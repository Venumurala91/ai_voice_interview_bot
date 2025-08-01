import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import InterviewList from './InterviewList';
import CreateInterview from './CreateInterview';

function App() {
  return (
    <Router>
      <div style={{ padding: '2rem', fontFamily: 'Arial, sans-serif', maxWidth: '900px', margin: 'auto' }}>
        <header style={{ marginBottom: '2rem', borderBottom: '2px solid #eee', paddingBottom: '1rem' }}>
          <Link to="/" style={{ textDecoration: 'none', color: '#1a1a1a', fontSize: '1.75rem', fontWeight: 'bold' }}>
            🤖 Voice AI Screening Dashboard
          </Link>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<InterviewList />} />
            <Route path="/create" element={<CreateInterview />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
export default App;