import { useState } from 'react';
import './App.css';

function App() {
  const [searchTerm, setSearchTerm] = useState('');
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchedGame, setSearchedGame] = useState(''); // To display what was searched for
  const [prioritizeSeries, setPrioritizeSeries] = useState(false);

  const API_BASE_URL = 'http://localhost:8000'; // Your FastAPI backend URL

  const fetchRecommendations = async (gameName) => {
    if (!gameName.trim()) {
      setRecommendations([]);
      setError(null);
      setSearchedGame('');
      return;
    }

    setLoading(true);
    setError(null);
    setSearchedGame(gameName); // Set the game name that was searched

    try {
      // Encode the game name to handle spaces and special characters in the URL
      const encodedGameName = encodeURIComponent(gameName);
      const response = await fetch(`${API_BASE_URL}/recommendations/${encodedGameName}?top_n=5&prioritize_series=${prioritizeSeries}`);
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Error: ${response.status}`);
      }
      
      const data = await response.json();
      setRecommendations(data);
    } catch (err) {
      console.error("Failed to fetch recommendations:", err);
      setError(err.message);
      setRecommendations([]); // Clear previous recommendations on error
    } finally {
      setLoading(false);
    }
  };

  const handleSearchChange = (event) => {
    setSearchTerm(event.target.value);
  };

  const handlePrioritizeSeriesChange = (event) => {
    setPrioritizeSeries(event.target.checked);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter') {
      fetchRecommendations(searchTerm);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault(); // Prevent form submission from reloading the page
    fetchRecommendations(searchTerm);
  }

  return (
    <div className="App">
      <h1>Game Recommendation Finder</h1>
      <form onSubmit={handleSubmit} className="search-form">
        <input
          type="text"
          placeholder="Enter a game name..."
          value={searchTerm}
          onChange={handleSearchChange}
          onKeyDown={handleKeyDown} // Optional: if you want Enter in input to also submit
          className="search-input"
        />
        <button type="submit" disabled={loading} className="search-button">
          {loading ? 'Searching...' : 'Search'}
        </button>
      </form>
      <div className="options-bar"> {/* Wrapper for checkbox */}
        <label htmlFor="prioritize-series-checkbox">
          <input
            type="checkbox"
            id="prioritize-series-checkbox"
            checked={prioritizeSeries}
            onChange={handlePrioritizeSeriesChange}
          />
          Prioritize games from the same series
        </label>
      </div>

      {error && <p className="error-message">Error: {error}</p>}

      {searchedGame && !loading && !error && (
        <h2>Recommendations for "{searchedGame}"</h2>
      )}

      {loading && <p>Loading recommendations...</p>}

      {!loading && recommendations.length > 0 && (
        <ul className="recommendations-list">
          {recommendations.map((game) => (
            <li key={game.id || game.name} className="recommendation-item">
              {game.cover_url && (
                <img src={game.cover_url} alt={`${game.name} cover`} className="game-cover" />
              )}
              <div className="game-info">
                <h3>{game.name} {game.from_same_collection && <span className="series-badge">(Series)</span>}</h3>
                <p className="game-score">Similarity Score: {game.score !== undefined ? game.score.toFixed(4) : 'N/A'}</p>
                {game.release_year && <p>Year: {game.release_year}</p>}
                {game.genres && game.genres.length > 0 && (
                  <p>Genres: {game.genres.join(', ')}</p>
                )}
                {game.themes && game.themes.length > 0 && (
                  <p>Themes: {game.themes.join(', ')}</p>
                )}
                {game.total_rating !== undefined && game.total_rating !== null && (
                  <p>Rating: {game.total_rating}/100</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {!loading && searchedGame && recommendations.length === 0 && !error && (
        <p>No recommendations found for "{searchedGame}".</p>
      )}
    </div>
  );
}

export default App;