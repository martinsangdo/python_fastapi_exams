import React, { useState, useEffect } from 'react';
import API from '../js/api';
import LoadingSpinner from '../js/components/LoadingSpinner';

const Homepage = () => {
  const [certifications, setCertifications] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCertificates = async () => {
      try {
        const response = await API.request('GET', '/exams/certifications');
        setCertifications(response.items);
      } catch (error) {
        console.error('Error fetching certificates:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchCertificates();
  }, []);

  return (
    <div className="homepage">
      {loading ? (
        <LoadingSpinner />
      ) : (
        <div className="certifications-list">
          {certifications.map((certification) => (
            <div key={certification.id} className="certification-item">
              <h2>{certification.name}</h2>
              <p>{certification.short_brief}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Homepage;
