import { useState, useEffect, useCallback } from 'react';
import './App.css';

function App() {
  const [searchTerm, setSearchTerm] = useState('');
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchedGame, setSearchedGame] = useState(''); // To display what was searched for
  const [prioritizeSeries, setPrioritizeSeries] = useState(false);
  const [suggestions, setSuggestions] = useState([]); // State for search suggestions
  const [isSuggestionsVisible, setIsSuggestionsVisible] = useState(false); // Control visibility

  const API_BASE_URL = 'http://localhost:8000'; // Your FastAPI backend URL

  // Debounce function
  const debounce = (func, delay) => {
    let timeoutId;
    return (...args) => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        func.apply(this, args);
      }, delay);
    };
  };

  const fetchGameSuggestions = async (query) => {
    if (!query.trim() || query.length < 2) { // Only search if query is not empty and has some length
      setSuggestions([]);
      setIsSuggestionsVisible(false);
      return;
    }
    try {
      const encodedQuery = encodeURIComponent(query);
      const response = await fetch(`${API_BASE_URL}/search-games?query=${encodedQuery}&limit=5`);
      if (!response.ok) {
        // Don't necessarily throw a blocking error for suggestions
        console.error("Failed to fetch suggestions:", response.status);
        setSuggestions([]);
        setIsSuggestionsVisible(false);
        return;
      }
      const data = await response.json();
      setSuggestions(data);
      setIsSuggestionsVisible(data.length > 0);
    } catch (err) {
      console.error("Error fetching suggestions:", err);
      setSuggestions([]);
      setIsSuggestionsVisible(false);
    }
  };

  // Create a debounced version of fetchGameSuggestions
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const debouncedFetchSuggestions = useCallback(debounce(fetchGameSuggestions, 500), []);

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
    setSuggestions([]); // Hide suggestions when a full search is made
    setIsSuggestionsVisible(false);

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
    const newSearchTerm = event.target.value;
    setSearchTerm(newSearchTerm);
    debouncedFetchSuggestions(newSearchTerm);
  };

  const handleSuggestionClick = (gameName) => {
    setSearchTerm(gameName);
    setSuggestions([]);
    setIsSuggestionsVisible(false);
    fetchRecommendations(gameName); // Optionally trigger search directly
  };

  const handlePrioritizeSeriesChange = (event) => {
    setPrioritizeSeries(event.target.checked);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter') {
      setIsSuggestionsVisible(false); // Hide suggestions on Enter
      fetchRecommendations(searchTerm);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    setIsSuggestionsVisible(false); // Hide suggestions on submit
    fetchRecommendations(searchTerm);
  }

  // Hide suggestions if clicked outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (event.target.closest('.search-container')) return; // Ignore clicks inside search container
      setIsSuggestionsVisible(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  return (
    <div className="App">
      <h1>Game Recommendation Finder</h1>
      <div className="search-container"> 
        <form onSubmit={handleSubmit} className="search-form">
          <input
            type="text"
            placeholder="Enter a game name..."
            value={searchTerm}
            onChange={handleSearchChange}
            onKeyDown={handleKeyDown}
            className="search-input"
            onFocus={() => setIsSuggestionsVisible(suggestions.length > 0 && searchTerm.length > 0)} // Show on focus if suggestions exist
          />
          <button type="submit" disabled={loading} className="search-button">
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>
        {isSuggestionsVisible && suggestions.length > 0 && (
          <ul className="suggestions-list">
            {suggestions.map((game) => (
              <li key={game.id} onClick={() => handleSuggestionClick(game.name)} className="suggestion-item">
                {game.cover_url && (
                  <img src={game.cover_url} alt={`${game.name} cover`} className="suggestion-cover" />
                )}
                <div className="suggestion-info">
                  <span className="suggestion-name">{game.name}</span>
                  {game.release_year && (
                    <span className="suggestion-year">({game.release_year})</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
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