from fastapi import FastAPI, HTTPException
import pymongo
from typing import List, Dict, Any, Set

# --- MongoDB Connection Details (should match your main.py) ---
MONGO_CONNECTION_STRING = "mongodb://localhost:27017/"
MONGO_DB_NAME = "igdb_data"
MONGO_GAMES_COLLECTION_NAME = "games"  # Collection where game data is stored
# --- ---

app = FastAPI(
    title="Video Game Recommendation API",
    description="Provides game recommendations based on Jaccard similarity of genres, keywords, and themes.",
    version="1.0.0"
)

# --- MongoDB Client ---
# It's generally recommended to manage client lifecycle with startup/shutdown events for production
# For simplicity here, we'll create it on demand or keep it global.
# For a more robust solution, consider FastAPI's dependency injection for DB connections.
mongo_client = None
games_collection = None

@app.on_event("startup")
async def startup_db_client():
    global mongo_client, games_collection
    mongo_client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    db = mongo_client[MONGO_DB_NAME]
    games_collection = db[MONGO_GAMES_COLLECTION_NAME]
    # Ensure index for faster lookups on name (if not already created by main.py on 'id')
    # main.py creates an index on 'id'. For name lookups, a text index or regex on a regular index is used.
    # games_collection.create_index([("name", pymongo.TEXT)], background=True) # Optional: for text search
    print(f"Connected to MongoDB database: '{MONGO_DB_NAME}', collection: '{MONGO_GAMES_COLLECTION_NAME}'")

@app.on_event("shutdown")
async def shutdown_db_client():
    global mongo_client
    if mongo_client:
        mongo_client.close()
        print("MongoDB connection closed.")

def calculate_jaccard_similarity(set1: Set[Any], set2: Set[Any]) -> float:
    if not set1 and not set2:
        return 1.0  # Both empty, consider them perfectly similar
    if not set1 or not set2:
        return 0.0  # One is empty, the other is not
    
    intersection_len = len(set1.intersection(set2))
    union_len = len(set1.union(set2))
    
    return intersection_len / union_len if union_len != 0 else 0.0

def _extract_values_from_list_of_objects(data_list: List[Dict[str, Any]], key_name: str = 'id') -> Set[Any]: # Changed default key_name to 'id' and return type to Set[Any]
    """Helper to extract a given key's value (default 'id') from a list of objects if they exist."""
    if not data_list or not isinstance(data_list, list):
        print(data_list) # Your debug print
        return set()
    # Ensure the value from item.get(key_name) is not None before adding to set,
    # as IGDB IDs are positive integers and should be truthy.
    # If an ID could be 0, and 0 is a valid ID you want to include, this condition might need adjustment.
    # However, IGDB IDs are typically positive.
    extracted_values = set()
    for item in data_list:
        if item and isinstance(item, dict):
            value = item.get(key_name)
            if value is not None: # Explicitly check for None, as 0 could be a valid ID in other contexts
                extracted_values.add(value)
    return extracted_values

def recommend_games_from_mongo(
    liked_game_name: str,
    collection: pymongo.collection.Collection,
    top_n: int = 5,
    genre_weight: float = 0.4,
    keyword_weight: float = 0.3, # Adjusted from your recommend.py to sum to 1 with themes
    theme_weight: float = 0.3
) -> List[Dict[str, Any]]:
    
    # Find the seed game by name (case-insensitive regex search)
    # Using a regex for case-insensitivity. For exact match, just use liked_game_name.
    seed_game = collection.find_one({"name": {"$regex": f"^{liked_game_name}$", "$options": "i"}})

    if not seed_game:
        raise HTTPException(status_code=404, detail=f"Game '{liked_game_name}' not found in the database.")

    seed_genres = set(seed_game.get('genres', []))
    seed_keywords = set(seed_game.get('keywords', []))
    seed_themes = set(seed_game.get('themes', []))

    recommendations = []
    
    # Query for other games. Project only necessary fields.
    # Exclude the seed game itself.
    query_filter = {"id": {"$ne": seed_game.get('id')}}
    projection = {"name": 1, "id": 1, "genres": 1, "keywords": 1, "themes": 1, "_id": 0}
    
    # Iterate through all other games in the database
    # For very large datasets, consider more optimized querying or pre-computation
    for game in collection.find(query_filter, projection):
        current_genres = set(game.get('genres', []))
        current_keywords = set(game.get('keywords', []))
        current_themes = set(game.get('themes', []))
        genre_sim = calculate_jaccard_similarity(seed_genres, current_genres)
        keyword_sim = calculate_jaccard_similarity(seed_keywords, current_keywords)
        theme_sim = calculate_jaccard_similarity(seed_themes, current_themes)
        
        total_similarity = (genre_weight * genre_sim) + \
                           (keyword_weight * keyword_sim) + \
                           (theme_weight * theme_sim)
        
        if total_similarity > 0:
            recommendations.append({
                'name': game.get('name'),
                'score': total_similarity, # Round score for cleaner output
                'id': game.get('id')
            })

    recommendations.sort(key=lambda x: x['score'], reverse=True)
    return recommendations[:top_n]

@app.get("/recommendations/{game_name}", response_model=List[Dict[str, Any]])
async def get_recommendations_for_game(game_name: str, top_n: int = 5):
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
            collection=games_collection,
            top_n=top_n
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
