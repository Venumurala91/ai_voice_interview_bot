import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';

const InterviewList = () => {
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchInterviews = () => {
      axios.get('/api/interviews')
        .then(res => setInterviews(res.data))
        .catch(err => console.error("Error fetching interviews:", err))
        .finally(() => setLoading(false));
    };
    fetchInterviews();
  }, []);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>All Interviews</h2>
        <Link to="/create" style={{ padding: '10px 15px', backgroundColor: '#007bff', color: 'white', textDecoration: 'none', borderRadius: '5px', fontWeight: 'bold' }}>
          + Create New Interview
        </Link>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #ddd', backgroundColor: '#f7f7f7' }}>
            <th style={{ padding: '12px', textAlign: 'left' }}>Candidate</th>
            <th style={{ padding: '12px', textAlign: 'left' }}>Position</th>
            <th style={{ padding: '12px', textAlign: 'left' }}>Status</th>
            <th style={{ padding: '12px', textAlign: 'left' }}>Created At</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan="4" style={{ textAlign: 'center', padding: '20px' }}>Loading...</td></tr>
          ) : interviews.length > 0 ? interviews.map(interview => (
            <tr key={interview.id} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: '12px' }}>{interview.candidate_name}</td>
              <td style={{ padding: '12px' }}>{interview.job_position}</td>
              <td style={{ padding: '12px', textTransform: 'capitalize' }}>{interview.status.replace('_', ' ')}</td>
              <td style={{ padding: '12px' }}>{new Date(interview.created_at).toLocaleString()}</td>
            </tr>
          )) : (
            <tr><td colSpan="4" style={{ textAlign: 'center', padding: '20px' }}>No interviews created yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
};
export default InterviewList;