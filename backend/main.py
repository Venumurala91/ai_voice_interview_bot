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

# Direct imports for local execution
import models
import database

load_dotenv()
models.Base.metadata.create_all(bind=database.engine)

# --- Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")
NGROK_URL = os.getenv("NGROK_URL")
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
redis_client = redis.from_url(REDIS_URL)
app = FastAPI(title="Voice AI Backend")

class InterviewCreate(BaseModel):
    candidate_name: str
    candidate_phone: str
    job_position: str
    job_description: str
    skills_to_assess: List[str]

@app.get("/health")
def health_check():
    return {"status": "healthy"}

async def call_google_ai(prompt: str) -> str:
    try:
        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Google AI: {e}")
        return "Error: AI response generation failed."

def make_plivo_call(to_number: str, interview_id: str):
    answer_url = f"{NGROK_URL}/voice/answer/{interview_id}"
    plivo_url = f"https://api.plivo.com/v1/Account/{PLIVO_AUTH_ID}/Call/"
    auth = (PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
    payload = {'from': PLIVO_PHONE_NUMBER, 'to': to_number, 'answer_url': answer_url}
    try:
        requests.post(plivo_url, auth=auth, json=payload, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"Failed to initiate call for {interview_id}: {e}")

@app.post("/api/interviews/create")
async def create_interview(data: InterviewCreate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    db_interview = models.Interview(
        candidate_name=data.candidate_name, candidate_phone=data.candidate_phone,
        job_position=data.job_position, status="generating_questions"
    )
    db.add(db_interview)
    db.commit()
    db.refresh(db_interview)
    interview_id = str(db_interview.id)
    
    prompt = f"""Generate 5 interview questions for this position:
    Job Position: {data.job_position}, Description: {data.job_description}, Skills: {', '.join(data.skills_to_assess)}.
    Return ONLY a JSON array of strings: ["Question 1", ...]"""
    
    questions_text = await call_google_ai(prompt)
    try:
        json_start = questions_text.find('[')
        json_end = questions_text.rfind(']') + 1
        questions = json.loads(questions_text[json_start:json_end])
    except (json.JSONDecodeError, IndexError):
        questions = ["Tell me about yourself.", "What are your strengths?"]

    db_interview.questions = questions
    db_interview.status = "ready_to_call"
    db.commit()
    
    redis_client.set(f"interview:{interview_id}:questions", json.dumps(questions))
    background_tasks.add_task(make_plivo_call, data.candidate_phone, interview_id)
    return {"interview_id": interview_id, "status": "Interview created."}

@app.get("/api/interviews")
def get_interviews(db: Session = Depends(database.get_db)):
    return db.query(models.Interview).order_by(models.Interview.created_at.desc()).all()

@app.post("/voice/answer/{interview_id}", response_class=PlainTextResponse)
async def handle_call_answer(interview_id: str, db: Session = Depends(database.get_db)):
    questions_json = redis_client.get(f"interview:{interview_id}:questions")
    if not questions_json:
        return '<Response><Say>Sorry, I could not find interview questions.</Say><Hangup/></Response>'
    
    questions = json.loads(questions_json)
    db.query(models.Interview).filter(models.Interview.id == uuid.UUID(interview_id)).update({"status": "in_progress"})
    db.commit()
    
    redis_client.set(f"interview:{interview_id}:current_question", 0)
    process_response_url = f"{NGROK_URL}/voice/process-response/{interview_id}"
    xml = f'<Response><Say>Hello. This is an automated screening call. Let\'s begin.</Say><Pause length="1"/><Say>{questions[0]}</Say><Record action="{process_response_url}" method="POST" playBeep="true"/></Response>'
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
        xml = f'<Response><Say>Next question.</Say><Pause length="1"/><Say>{next_question}</Say><Record action="{process_response_url}" method="POST" playBeep="true"/></Response>'
    else:
        interview.status = "completed"
        db.commit()
        xml = '<Response><Say>Thank you. The interview is complete.</Say><Hangup/></Response>'
    return xml