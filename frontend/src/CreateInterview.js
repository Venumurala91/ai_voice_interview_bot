import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const CreateInterview = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({ candidate_name: '', candidate_phone: '', job_position: '', job_description: '', skills_to_assess: '' });
  const [isLoading, setIsLoading] = useState(false);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setIsLoading(true);
    const payload = { ...formData, skills_to_assess: formData.skills_to_assess.split(',').map(s => s.trim()).filter(Boolean) };
    
    axios.post('/api/interviews/create', payload)
      .then(() => {
        alert(`Success! Interview created for ${formData.candidate_name}.`);
        navigate('/');
      })
      .catch(err => {
        console.error('Error creating interview:', err);
        alert('Failed to create interview. Check console for details.');
      })
      .finally(() => setIsLoading(false));
  };

  const styles = {
    form: { display: 'flex', flexDirection: 'column', maxWidth: '600px', gap: '15px' },
    label: { fontWeight: 'bold', marginBottom: '-10px' },
    input: { padding: '12px', fontSize: '1rem', border: '1px solid #ccc', borderRadius: '5px' },
    button: { padding: '12px', fontSize: '1rem', backgroundColor: isLoading ? '#aaa' : '#28a745', color: 'white', border: 'none', cursor: 'pointer', borderRadius: '5px', fontWeight: 'bold' }
  };

  return (
    <div>
      <h2 style={{ marginBottom: '1.5rem' }}>Create a New AI Interview</h2>
      <form onSubmit={handleSubmit} style={styles.form}>
        <label style={styles.label}>Candidate Name</label>
        <input name="candidate_name" value={formData.candidate_name} onChange={handleInputChange} style={styles.input} required />
        <label style={styles.label}>Candidate Phone Number</label>
        <input name="candidate_phone" value={formData.candidate_phone} onChange={handleInputChange} placeholder="Use international format, e.g., +919876543210" style={styles.input} required />
        <label style={styles.label}>Job Position</label>
        <input name="job_position" value={formData.job_position} onChange={handleInputChange} style={styles.input} required />
        <label style={styles.label}>Full Job Description</label>
        <textarea name="job_description" value={formData.job_description} onChange={handleInputChange} style={{...styles.input, height: '120px', fontFamily: 'inherit'}} required />
        <label style={styles.label}>Skills to Assess (comma-separated)</label>
        <input name="skills_to_assess" value={formData.skills_to_assess} onChange={handleInputChange} placeholder="e.g., Python, FastAPI, React" style={styles.input} required />
        <button type="submit" style={styles.button} disabled={isLoading}>
          {isLoading ? 'Creating Interview...' : '🚀 Start AI Interview Call'}
        </button>
      </form>
    </div>
  );
};
export default CreateInterview;