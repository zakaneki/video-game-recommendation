# Video Game Recommendation System

This project is a video game recommendation system that uses a FastAPI backend and a React frontend. It fetches game data from the IGDB API, stores it in MongoDB, and uses Meilisearch for fast game title searching and suggestions. Recommendations are generated based on Jaccard similarity of game genres, keywords, and themes.

## Project Structure

```
.
├── backend-fastapi/        # FastAPI backend application
│   ├── api.py              # Main API logic, endpoints for search and recommendations
│   ├── main.py             # Script to fetch data from IGDB, store in MongoDB, and index in Meilisearch
│   └── requirements.txt    # Python dependencies
├── frontend-vite-react/    # React frontend application
│   ├── src/                # React components and application logic
│   ├── vite.config.js      # Vite configuration
│   └── package.json        # Node.js dependencies
└── README.md               # This file
```

## How it Works

### Backend (`backend-fastapi`)

1.  **Data Ingestion (`main.py`):**
    *   Connects to the IGDB API to fetch comprehensive data about video games, genres, themes, covers, etc.
    *   Stores this data in a MongoDB database.
    *   Indexes essential game information (ID, name, parent game, version parent, game type, cover URL, release year) into a Meilisearch instance for optimized search performance.
    *   `main.py` is intended to be run as a script to populate and update the database and search index.

2.  **API (`api.py`):**
    *   Provides a RESTful API built with FastAPI.
    *   **Endpoints:**
        *   `/search-games`: Takes a query string and returns a list of game suggestions (name, ID, cover, release year) from Meilisearch, filtering out DLCs and expansions.
        *   `/recommendations/{game_name}`: Takes a game name, finds it in the MongoDB database, and then calculates Jaccard similarity scores with other games based on shared genres, keywords, and themes. It returns a list of recommended games, optionally prioritizing games from the same series.
    *   Uses a `lifespan` manager to handle MongoDB and Meilisearch client connections.

### Frontend (`frontend-vite-react`)

1.  **User Interface:**
    *   A React application built with Vite.
    *   Provides a search bar for users to type in a game name.
    *   As the user types, it queries the backend's `/search-games` endpoint to display live suggestions.
    *   Users can click a suggestion or submit their search term to get recommendations.
2.  **Recommendation Display:**
    *   Fetches recommendations from the backend's `/recommendations/{game_name}` endpoint.
    *   Displays a list of recommended games, including their cover image, name, similarity score, release year, genres, themes, and rating.
    *   Includes an option to "Prioritize games from the same series," which adjusts the recommendation logic on the backend.

## Prerequisites

*   **Python 3.8+**
*   **Node.js and npm** (or yarn)
*   **MongoDB instance** running and accessible.
*   **Meilisearch instance** running and accessible.
*   **IGDB API Credentials** (Client ID and Client Secret) - You can get these by registering an application on the [Twitch Developer Portal](https://dev.twitch.tv/docs/igdb).

## Setup and Running

### 1. Clone the Repository

```bash
git clone https://github.com/zakaneki/video-game-recommendation.git
cd video-game-recommendation
```

### 2. Backend Setup (`backend-fastapi`)

   a.  **Navigate to the backend directory:**
       ```bash
       cd backend-fastapi
       ```

   b.  **Create a virtual environment (recommended):**
       ```bash
       python -m venv venv
       source venv/bin/activate  # On Windows: venv\Scripts\activate
       ```

   c.  **Install Python dependencies:**
       ```bash
       pip install -r requirements.txt
       ```

   d.  **Set up environment variables:**
       Create a `.env` file in the `backend-fastapi` directory with your credentials and configurations. You can copy `.env.example` if one exists, or create it manually:

       ```env
       # .env
       CLIENT_ID="YOUR_TWITCH_CLIENT_ID"
       CLIENT_SECRET="YOUR_TWITCH_CLIENT_SECRET"
       MONGO_CONNECTION_STRING="mongodb://localhost:27017/" # Or your MongoDB Atlas string
       MEILI_HOST_URL="http://localhost:7700"
       MEILI_MASTER_KEY="YOUR_MEILISEARCH_MASTER_KEY" # Optional, but recommended for production
       ```
       *   Replace placeholders with your actual IGDB Client ID, Client Secret, MongoDB connection string, Meilisearch URL, and Meilisearch Master Key (if you've set one).

   e.  **Populate Database and Meilisearch Index:**
       Run the `main.py` script. This will fetch data from IGDB, store it in MongoDB, and create/update the Meilisearch index. This might take a while depending on the amount of data.
       ```bash
       python main.py
       ```
       Ensure MongoDB and Meilisearch are running before executing this script.

   f.  **Run the FastAPI application:**
       ```bash
       uvicorn api:app --reload
       ```
       The API will typically be available at `http://127.0.0.1:8000`. You can access the OpenAPI documentation at `http://127.0.0.1:8000/docs`.

### 3. Frontend Setup (`frontend-vite-react`)

   a.  **Navigate to the frontend directory (from the project root):**
       ```bash
       cd ../frontend-vite-react
       ```
       Or, if you are in `backend-fastapi`, use `cd ../frontend-vite-react`.

   b.  **Install Node.js dependencies:**
       ```bash
       npm install
       # or
       # yarn install
       ```

   c.  **Run the React development server:**
       ```bash
       npm run dev
       # or
       # yarn dev
       ```
       The frontend application will typically be available at `http://localhost:5173`.

### 4. Accessing the Application

*   Open your browser and navigate to the frontend URL (e.g., `http://localhost:5173`).
*   Start typing a game name in the search bar to see suggestions.
*   Select a game or press Enter to get recommendations.

## Notes

*   The `main.py` script in the backend is designed to delete existing data in the specified MongoDB collections and Meilisearch index before fetching new data. Be cautious if you have other data in those collections/indexes.
*   The IGDB API has rate limits. The `main.py` script includes basic handling for 429 (Too Many Requests) errors by pausing, but extensive fetching might still hit limits.
