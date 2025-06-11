from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pymongo
from typing import List, Dict, Any, Set
from datetime import datetime
import meilisearch
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
# --- Meilisearch Connection Details ---
MEILI_HOST_URL = os.environ.get("MEILI_HOST_URL", "http://localhost:7700")
MEILI_MASTER_KEY = os.environ.get("MEILI_MASTER_KEY") # Set your master key if you have one (recommended for production)
MEILI_INDEX_NAME = "games"
# --- ---


# --- MongoDB Connection Details (should match your main.py) ---
MONGO_CONNECTION_STRING = os.environ.get("MONGO_CONNECTION_STRING","mongodb://localhost:27017/") 
MONGO_DB_NAME = "igdb_data"
MONGO_GAMES_COLLECTION_NAME = "games"  # Collection where game data is stored
MONGO_COVERS_COLLECTION_NAME = "covers"
MONGO_GENRES_COLLECTION_NAME = "genres"
MONGO_THEMES_COLLECTION_NAME = "themes"
# --- ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    global mongo_client, db, games_collection, covers_collection, genres_collection, themes_collection
    global meili_client
    
    mongo_client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    db = mongo_client[MONGO_DB_NAME]
    games_collection = db[MONGO_GAMES_COLLECTION_NAME]
    covers_collection = db[MONGO_COVERS_COLLECTION_NAME]
    genres_collection = db[MONGO_GENRES_COLLECTION_NAME]
    themes_collection = db[MONGO_THEMES_COLLECTION_NAME]
    print(f"Connected to MongoDB database: '{MONGO_DB_NAME}', collection: '{MONGO_GAMES_COLLECTION_NAME}'")

    try:
        meili_client = meilisearch.Client(MEILI_HOST_URL, MEILI_MASTER_KEY)
        index = meili_client.index("games")
        index.update_filterable_attributes(["parent_game", "version_parent", "game_type"])
        print(f"Connected to Meilisearch at {MEILI_HOST_URL}, index: '{MEILI_INDEX_NAME}'")
    except Exception as e:
        print(f"Error connecting to Meilisearch: {e}")
        meili_client = None
    
    yield
    
    # Shutdown logic
    if mongo_client:
        mongo_client.close()
        print("MongoDB connection closed.")

app = FastAPI(
    title="Video Game Recommendation API",
    description="Provides game recommendations based on Jaccard similarity of genres, keywords, and themes.",
    version="1.0.0",
    lifespan=lifespan
)

# --- CORS Middleware ---
origins = [
    "http://localhost:5173",  # Your Vite React frontend development server
    # Add other origins if needed, e.g., your deployed frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)


# --- Global variables for clients and collections ---
mongo_client: pymongo.MongoClient = None
db: pymongo.database.Database = None
games_collection: pymongo.collection.Collection = None
covers_collection: pymongo.collection.Collection = None
genres_collection: pymongo.collection.Collection = None
themes_collection: pymongo.collection.Collection = None
meili_client: meilisearch.Client = None

def calculate_jaccard_similarity(set1: Set[Any], set2: Set[Any]) -> float:
    intersection_len = len(set1.intersection(set2))
    union_len = len(set1.union(set2))
    
    if union_len == 0: # This implies both sets were empty
        return 0.0
    
    return intersection_len / union_len

def recommend_games_from_mongo(
    liked_game_name: str,
    current_db: pymongo.database.Database,
    top_n: int = 5,
    genre_weight: float = 0.4,
    keyword_weight: float = 0.3,
    theme_weight: float = 0.3,
    prioritize_series: bool = False,
    series_bonus: float = 0.5
) -> List[Dict[str, Any]]:
    
    game_coll = current_db[MONGO_GAMES_COLLECTION_NAME]
    cover_coll = current_db[MONGO_COVERS_COLLECTION_NAME]
    genre_coll = current_db[MONGO_GENRES_COLLECTION_NAME]
    theme_coll = current_db[MONGO_THEMES_COLLECTION_NAME]
    
    # Find the seed game by name (case-insensitive regex search)
    # Using a regex for case-insensitivity. For exact match, just use liked_game_name.
    seed_game = game_coll.find_one({"name": {"$regex": f"^{liked_game_name}$", "$options": "i"}})

    if not seed_game:
        raise HTTPException(status_code=404, detail=f"Game '{liked_game_name}' not found in the database.")

    seed_genres = set(seed_game.get('genres', []))
    seed_keywords = set(seed_game.get('keywords', []))
    seed_themes = set(seed_game.get('themes', []))
    seed_collection_ids = set(seed_game.get('collections', []))

    recommendations_data = []
    
    # Query for other games. Project only necessary fields.
    # Exclude the seed game itself.
    query_filter = {"id": {"$ne": seed_game.get('id')}}
    projection = {
        "name": 1, "id": 1,
        "genres": 1, "keywords": 1, "themes": 1, # Keep for similarity and display names
        "cover": 1,                             # For cover image
        "first_release_date": 1,                # For release year
        "total_rating": 1,                      # For total rating
        "collections": 1,
        "version_parent": 1,
        "parent_game": 1,
        "game_type": 1,
        "_id": 0
    }
    
    potential_recommendations = []

    # Iterate through all other games in the database
    # For very large datasets, consider more optimized querying or pre-computation
    for game in game_coll.find(query_filter, projection):
        current_genres = set(game.get('genres', []))
        current_keywords = set(game.get('keywords', []))
        current_themes = set(game.get('themes', []))

        genre_sim = calculate_jaccard_similarity(seed_genres, current_genres)
        keyword_sim = calculate_jaccard_similarity(seed_keywords, current_keywords)
        theme_sim = calculate_jaccard_similarity(seed_themes, current_themes)
        
        total_similarity = (genre_weight * genre_sim) + \
                           (keyword_weight * keyword_sim) + \
                           (theme_weight * theme_sim)
        
        from_same_collection = False
        if prioritize_series:
            candidate_collection_ids = set(game.get('collections', []))
            if len(seed_collection_ids.intersection(candidate_collection_ids)) > 0:
                if (game.get('version_parent') == seed_game.get('id')) or (seed_game.get('version_parent') == game.get('id')):
                    # If the game is a version of the liked game, we don't want to recommend it
                    continue
                if game.get('id') in seed_game.get('remasters', []) or seed_game.get('id') in game.get('remasters', []):
                    # If the game is a remaster of the liked game, we don't want to recommend it
                    continue
                total_similarity += series_bonus
                from_same_collection = True
                   
        if total_similarity > 0 and game.get('version_parent') is None and (game.get('parent_game') is None or game.get('parent_game') == seed_game.get('id')) and game.get('game_type') != 14:
            potential_recommendations.append({
                'game_data': game,
                'score': total_similarity,
                'from_same_collection': from_same_collection
            })

    potential_recommendations.sort(key=lambda x: x['score'], reverse=True)
    top_potentials = potential_recommendations[:top_n]

    for rec_item in top_potentials:
        game = rec_item['game_data'] # The game document from 'games' collection
        
        cover_url = None
        cover_id = game.get('cover') # Assuming this is the ID for the 'covers' collection
        if cover_id:
            cover_doc = cover_coll.find_one({"id": cover_id})
            if cover_doc:
                # Extract the last part after the last '/' in cover_doc['url']
                url = cover_doc.get('url')
                if url:
                    cover_url = "https://images.igdb.com/igdb/image/upload/t_cover_big/" + url.split('/')[-1]
        
        release_year = None
        first_release_timestamp = game.get('first_release_date')
        if first_release_timestamp:
            try:
                release_year = datetime.fromtimestamp(first_release_timestamp).year
            except (TypeError, ValueError):
                pass 
        
        genre_names = []
        genre_ids = game.get('genres', []) # List of genre IDs
        if genre_ids:
            genre_docs = genre_coll.find({"id": {"$in": genre_ids}}, {"name": 1, "_id": 0})
            genre_names = [g_doc.get('name') for g_doc in genre_docs if g_doc.get('name')]
            
        theme_names = []
        theme_ids = game.get('themes', []) # List of theme IDs
        if theme_ids:
            theme_docs = theme_coll.find({"id": {"$in": theme_ids}}, {"name": 1, "_id": 0})
            theme_names = [t_doc.get('name') for t_doc in theme_docs if t_doc.get('name')]
        
        total_rating_value = game.get('total_rating')
        total_rating_display = round(total_rating_value) if total_rating_value is not None else None

        recommendations_data.append({
            'name': game.get('name'),
            'score': round(rec_item['score'], 4),
            'id': game.get('id'),
            'cover_url': cover_url,
            'release_year': release_year,
            'genres': genre_names,
            'themes': theme_names,
            'total_rating': total_rating_display,
            'from_same_collection': rec_item['from_same_collection'],
        })

    return recommendations_data

@app.get("/search-games", response_model=List[Dict[str, Any]])
async def search_games_for_suggestions(query: str, limit: int = 5):
    """
    Provides game name suggestions based on a search query,
    filtering out DLCs, expansions, and specific game types.
    """
    if meili_client is None:
        raise HTTPException(status_code=503, detail="Search service not available.")

    try:
        index = meili_client.index(MEILI_INDEX_NAME)
        
        # Meilisearch filter syntax:
        # - To check for non-existence or null: "parent_game NOT EXISTS" or "parent_game IS NULL"
        #   (Meilisearch's behavior with non-existent vs null can vary, test this)
        #   A common way is to ensure the field is not present or explicitly null if your data has it.
        #   If `parent_game` is only present for DLCs, "parent_game NOT EXISTS" is good.
        #   If `parent_game` can be `null` for base games, then `(parent_game NOT EXISTS OR parent_game IS NULL)`
        # - For game_type, assuming 14 is DLC/Add-on
        # - For version_parent, assuming base games have this as null or non-existent
        
        # Let's assume for Meilisearch:
        # - Base games do NOT have a 'parent_game' attribute or it's null.
        # - Base games do NOT have a 'version_parent' attribute or it's null.
        # - We want to exclude game_type 14 (DLC/Add-on).
        # Meilisearch filter syntax is an array of strings or arrays of strings (for OR conditions)
        
        search_params = {
            'q': query,
            'limit': limit,
            'attributesToRetrieve': ['id', 'name', 'cover_url', 'release_year'], # Only fetch id and name
            'filter': [
                '(parent_game NOT EXISTS OR parent_game IS NULL)',
                '(version_parent NOT EXISTS OR version_parent IS NULL)',
                'game_type != 14' # Exclude game_type 14 (DLC/Add-on)
            ]
            # You might need to adjust the filter based on how your data is structured in Meilisearch
            # and Meilisearch's exact filtering capabilities for null/non-existent fields.
            # If `parent_game` is always present and `0` or `null` for base games, filter would be `parent_game = null` or `parent_game = 0`.
        }
        
        search_results = index.search(query, search_params)
        
        # Format results to a simple list of {'id': game_id, 'name': game_name}
        suggestions = []
        for hit in search_results.get('hits', []):
            suggestions.append({
                'id': hit.get('id'), 
                'name': hit.get('name'),
                'cover_url': hit.get('cover_url'), # Include cover_url
                'release_year': hit.get('release_year') # Include release_year
            })
            
        return suggestions
        
    except Exception as e:
        print(f"Error searching with Meilisearch: {e}")
        raise HTTPException(status_code=500, detail="Error performing search.")
    
@app.get("/recommendations/{game_name}", response_model=List[Dict[str, Any]])
async def get_recommendations_for_game(game_name: str, top_n: int = 5, prioritize_series: bool = False):
    """
    Get game recommendations based on a liked game.
    
    - **game_name**: The name of the game you liked.
    - **top_n**: The number of recommendations to return (default is 5).
    """
    if games_collection is None:
        raise HTTPException(status_code=503, detail="Database not initialized. Please try again shortly.")
    
    try:
        recommended_games = recommend_games_from_mongo(
            liked_game_name=game_name,
            current_db=db,
            top_n=top_n,
            prioritize_series=prioritize_series
        )
        if not recommended_games and games_collection.count_documents({"name": {"$regex": f"^{game_name}$", "$options": "i"}}) > 0 :
             # Seed game was found, but no recommendations generated
            return [] # Or a message like {"message": "Seed game found, but no similar games based on current criteria."}
        return recommended_games
    except HTTPException as e: # Re-raise HTTPExceptions (like 404)
        raise e
    except Exception as e:
        # Log the exception e for debugging
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred while generating recommendations.")

# To run this FastAPI application:
# 1. Save this code as api.py
# 2. Open your terminal in the same directory
# 3. Run: uvicorn api:app --reload
# 4. Open your browser and go to http://127.0.0.1:8000/docs to see the API documentation.
# Example request: http://127.0.0.1:8000/recommendations/Elden%20Ring?top_n=3
