import os
import uuid
import json
import requests
import redis
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv
import google.generativeai as genai
from sqlalchemy.orm import Session
import whisper  # For open-source transcription

# Local module imports
import models
import database

# Load environment variables from .env file
load_dotenv()

# Create database tables if they don't exist when the app starts
models.Base.metadata.create_all(bind=database.engine)

# --- Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")
NGROK_URL = os.getenv("NGROK_URL")
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER")

# --- AI & Cache Client Initialization ---
genai.configure(api_key=GOOGLE_API_KEY)
llm_model = genai.GenerativeModel('gemini-1.5-flash')
redis_client = redis.from_url(REDIS_URL)

# Load the Whisper model into memory on startup.
# "base" is a good balance of speed and accuracy for general use.
print("Loading Whisper model...")
whisper_model = whisper.load_model("base")
print("Whisper model loaded successfully.")

app = FastAPI(title="Voice AI Backend")

# --- Pydantic Models ---
class InterviewCreate(BaseModel):
    candidate_name: str
    candidate_phone: str
    job_position: str
    job_description: str
    skills_to_assess: List[str]

# --- Helper Functions ---
@app.get("/health")
def health_check():
    return {"status": "healthy"}

async def call_google_ai(prompt: str) -> str:
    try:
        response = await llm_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Google AI: {e}")
        return json.dumps({"error": "AI response generation failed."})

def transcribe_audio_with_whisper(audio_url: str) -> str:
    """Downloads an audio file and transcribes it using the local Whisper model."""
    try:
        audio_response = requests.get(audio_url)
        audio_response.raise_for_status()
        
        temp_audio_path = f"/tmp/{uuid.uuid4()}.mp3"
        with open(temp_audio_path, 'wb') as f:
            f.write(audio_response.content)
            
        result = whisper_model.transcribe(temp_audio_path, fp16=False)
        transcript = result["text"]
        
        os.remove(temp_audio_path)
        print(f"Whisper Transcript: {transcript}")
        return transcript
    except Exception as e:
        print(f"Error during Whisper transcription: {e}")
        return "Transcription failed."

async def generate_interview_report(interview_id: str, db: Session):
    """Generates a final AI report for a completed interview."""
    interview = db.query(models.Interview).filter(models.Interview.id == uuid.UUID(interview_id)).first()
    if not interview or not interview.responses: return

    full_conversation = ""
    for i, resp in enumerate(interview.responses):
        question = resp.get("question", f"Question {i+1}")
        recording_url = resp.get("recording_url")
        if recording_url:
            transcript = transcribe_audio_with_whisper(recording_url)
            full_conversation += f"Interviewer: {question}\nCandidate: {transcript}\n\n"

    if not full_conversation:
        interview.report = {"error": "No valid responses to analyze."}
        db.commit()
        return

    prompt = f"""
    You are an expert HR analyst. Based on the following interview transcript for a "{interview.job_position}" role,
    provide a structured performance report.

    Transcript:\n---\n{full_conversation}---\n
    Analyze the candidate's performance and provide your report ONLY in this exact JSON format:
    {{
      "overall_score": "A score from 1-10", "recommendation": "Strong Hire | Hire | Consider | No Hire",
      "summary": "A 2-3 sentence summary of the candidate's performance.",
      "strengths": ["Identified strength 1", "Identified strength 2"],
      "weaknesses": ["Identified weakness 1", "Identified weakness 2"]
    }}
    """
    report_text = await call_google_ai(prompt)
    try:
        json_start = report_text.find('{')
        json_end = report_text.rfind('}') + 1
        report_json = json.loads(report_text[json_start:json_end])
        interview.report = report_json
        interview.status = "report_ready"
        db.commit()
        print(f"Report generated for interview {interview_id}")
    except (json.JSONDecodeError, IndexError):
        print(f"Failed to parse AI report for interview {interview_id}")
        interview.report = {"error": "Failed to generate AI report."}
        db.commit()

def make_plivo_call(to_number: str, interview_id: str, db: Session):
    answer_url = f"{NGROK_URL}/voice/answer/{interview_id}"
    hangup_url = f"{NGROK_URL}/voice/hangup/{interview_id}"
    plivo_url = f"https://api.plivo.com/v1/Account/{PLIVO_AUTH_ID}/Call/"
    auth = (PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
    payload = {'from': PLIVO_PHONE_NUMBER, 'to': to_number, 'answer_url': answer_url, 'hangup_url': hangup_url}
    db_interview = db.query(models.Interview).filter(models.Interview.id == uuid.UUID(interview_id)).first()
    try:
        requests.post(plivo_url, auth=auth, json=payload, timeout=10)
        if db_interview: db_interview.status = "ringing"; db.commit()
    except requests.exceptions.RequestException as e:
        print(f"Failed to initiate call for {interview_id}: {e}")
        if db_interview: db_interview.status = "call_failed"; db.commit()

# --- API Endpoints ---
@app.post("/api/interviews/create")
async def create_interview(data: InterviewCreate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    db_interview = models.Interview(
        candidate_name=data.candidate_name, candidate_phone=data.candidate_phone,
        job_position=data.job_position, status="generating_questions"
    )
    db.add(db_interview); db.commit(); db.refresh(db_interview)
    interview_id = str(db_interview.id)
    
    prompt = f"""Generate 5 interview questions for a "{data.job_position}" role, assessing these skills: {', '.join(data.skills_to_assess)}. 
    Job Description: {data.job_description}.
    Return ONLY a JSON array of strings: ["Question 1", ...]"""
    
    questions_text = await call_google_ai(prompt)
    try:
        questions = json.loads(questions_text[questions_text.find('['):questions_text.rfind(']')+1])
    except:
        questions = ["Tell me about yourself.", "What are your strengths?"]

    db_interview.questions = questions; db_interview.status = "ready_to_call"; db.commit()
    
    redis_client.set(f"interview:{interview_id}:questions", json.dumps(questions))
    background_tasks.add_task(make_plivo_call, data.candidate_phone, interview_id, db)
    return {"interview_id": interview_id, "status": "Interview created."}

@app.post("/api/interviews/{interview_id}/call")
async def manual_call_trigger(interview_id: str, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    db_interview = db.query(models.Interview).filter(models.Interview.id == uuid.UUID(interview_id)).first()
    if not db_interview: raise HTTPException(status_code=404, detail="Interview not found")
    background_tasks.add_task(make_plivo_call, db_interview.candidate_phone, interview_id, db)
    return {"status": "Call initiated manually."}

@app.get("/api/interviews")
def get_interviews(db: Session = Depends(database.get_db)):
    return db.query(models.Interview).order_by(models.Interview.created_at.desc()).all()

# --- Voice Webhook Endpoints ---
@app.post("/voice/answer/{interview_id}", response_class=PlainTextResponse)
async def handle_call_answer(interview_id: str, db: Session = Depends(database.get_db)):
    questions_json = redis_client.get(f"interview:{interview_id}:questions")
    if not questions_json:
        return '<Response><Say>Sorry, I could not find the interview questions.</Say><Hangup/></Response>'
    
    questions = json.loads(questions_json)
    db.query(models.Interview).filter(models.Interview.id == uuid.UUID(interview_id)).update({"status": "in_progress"})
    db.commit()
    
    redis_client.set(f"interview:{interview_id}:current_question", 0)
    process_response_url = f"{NGROK_URL}/voice/process-response/{interview_id}"
    xml = f'<Response><Say>Hello. This is an automated screening call. Let\'s begin.</Say><Pause length="1"/><Say>{questions[0]}</Say><Record action="{process_response_url}" method="POST" playBeep="true" recordWhen="beep" trim="true"/></Response>'
    return xml

@app.post("/voice/process-response/{interview_id}", response_class=PlainTextResponse)
async def process_response(interview_id: str, request: Request, db: Session = Depends(database.get_db)):
    form = await request.form()
    recording_url = form.get("RecordingUrl")
    
    interview = db.query(models.Interview).filter(models.Interview.id == uuid.UUID(interview_id)).first()
    current_index = int(redis_client.get(f"interview:{interview_id}:current_question") or 0)
    
    current_responses = interview.responses or []
    current_responses.append({"question": interview.questions[current_index], "recording_url": recording_url})
    interview.responses = current_responses
    db.commit()

    next_index = current_index + 1
    if next_index < len(interview.questions):
        redis_client.set(f"interview:{interview_id}:current_question", next_index)
        next_question = interview.questions[next_index]
        process_response_url = f"{NGROK_URL}/voice/process-response/{interview_id}"
        xml = f'<Response><Say>Next question.</Say><Pause length="1"/><Say>{next_question}</Say><Record action="{process_response_url}" method="POST" playBeep="true" recordWhen="beep" trim="true"/></Response>'
    else:
        interview.status = "completed"
        db.commit()
        xml = '<Response><Say>Thank you. The interview is complete. We will be in touch shortly.</Say><Hangup/></Response>'
    return xml

@app.post("/voice/hangup/{interview_id}")
async def handle_hangup(interview_id: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    form = await request.form()
    call_status = form.get("CallStatus")

    db_interview = db.query(models.Interview).filter(models.Interview.id == uuid.UUID(interview_id)).first()
    if not db_interview: return {"status": "error"}

    # Only update status if the interview wasn't already marked 'completed' by our logic
    if db_interview.status != "completed":
        status_map = {'no-answer': 'no_answer', 'busy': 'busy', 'failed': 'call_failed', 'canceled': 'call_failed'}
        db_interview.status = status_map.get(call_status, 'call_failed')
        db.commit()

    # If the call was successfully completed, start generating the report
    if db_interview.status == "completed":
        background_tasks.add_task(generate_interview_report, interview_id, db)

    print(f"Call for interview {interview_id} ended with status: {call_status}")
    return {"status": "ok"}