import os
import requests
import pymongo # For MongoDB interaction
import time
import meilisearch
from datetime import datetime
import os

MEILI_HOST_URL = os.environ.get("MEILI_HOST_URL", "http://localhost:7700")
MEILI_MASTER_KEY = os.environ.get("MEILI_MASTER_KEY") # Use the same key you started Meilisearch with
MEILI_INDEX_NAME = "games"

# Replace with your actual Client ID and Client Secret
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")

# --- MongoDB Connection Details ---
MONGO_CONNECTION_STRING = os.environ.get("MONGO_CONNECTION_STRING","mongodb://localhost:27017/") # Default local MongoDB
MONGO_DB_NAME = "igdb_data"
# Collection names will be 'games', 'age_ratings', 'age_rating_content_descriptions_v2'
# --- ---
MONGO_COVERS_COLLECTION_NAME = "covers"

def setup_meilisearch_index(client):
    try:
        # Create index if it doesn't exist
        client.create_index(MEILI_INDEX_NAME, {'primaryKey': 'id'})
        print(f"Index '{MEILI_INDEX_NAME}' created or already exists.")
        
        index = client.index(MEILI_INDEX_NAME)

        # Configure filterable attributes (essential for your /search-games endpoint)
        filterable_attributes_task = index.update_filterable_attributes([
            'parent_game', 
            'version_parent', 
            'game_type'
        ])
        print(f"Update filterable attributes task: {filterable_attributes_task.task_uid}")
        
        # Configure searchable attributes (what fields Meilisearch should primarily search in)
        searchable_attributes_task = index.update_searchable_attributes([
            'name' # Most important for name-based search
            # You could add other fields like alternative_names if you index them
        ])
        print(f"Update searchable attributes task: {searchable_attributes_task.task_uid}")

        # Configure displayed attributes (what is returned in search results by default)
        # Your /search-games endpoint specifies 'attributesToRetrieve', so this is less critical for that specific endpoint
        # but good practice.
        displayed_attributes_task = index.update_displayed_attributes([
            'id',
            'name',
            'parent_game', # Useful for debugging filters
            'version_parent',
            'game_type',
            'cover_url',
            'release_year'
            # Add other fields you might want to see directly from Meilisearch
        ])
        print(f"Update displayed attributes task: {displayed_attributes_task.task_uid}")

        # Configure ranking rules (optional, but can fine-tune relevance)
        # Default ranking rules are usually good to start.
        # Example: index.update_ranking_rules([...])

        print("Meilisearch index configuration tasks submitted. Check task statuses for completion.")

    except Exception as e:
        print(f"Error setting up Meilisearch index '{MEILI_INDEX_NAME}': {e}")

def add_games_to_meilisearch(games_list: list, meili_client_instance, mongo_db_instance):
    if not meili_client_instance:
        print("Meilisearch client not initialized. Skipping add to Meilisearch.")
        return
    if not games_list:
        print("No games to add to Meilisearch.")
        return
    if mongo_db_instance is None:
        print("MongoDB instance not provided to add_games_to_meilisearch. Skipping.")
        return

    index = meili_client_instance.index(MEILI_INDEX_NAME)
    covers_collection = mongo_db_instance[MONGO_COVERS_COLLECTION_NAME]
    documents_to_add = []
    for game_doc in games_list:
        cover_url = None
        cover_id = game_doc.get('cover') # This is the ID of the cover document
        if cover_id:
            cover_info = covers_collection.find_one({"id": cover_id})
            if cover_info and cover_info.get('url'):
                # Using t_cover_small for suggestions, adjust if needed (e.g., t_thumb)
                cover_url = "https://images.igdb.com/igdb/image/upload/t_cover_small/" + cover_info.get('url').split('/')[-1]

        release_year = None
        first_release_timestamp = game_doc.get('first_release_date')
        if first_release_timestamp:
            try:
                if first_release_timestamp >= 0:
                    release_year = datetime.fromtimestamp(first_release_timestamp).year
                else:
                    # Manually calculate year for negative Unix timestamps (before 1970)
                    # 1 year = 31556952 seconds (average, accounting for leap years)
                    # 1970 + (timestamp / seconds_per_year)
                    seconds_per_year = 31556952
                    year = 1970 + int(first_release_timestamp // seconds_per_year)
                    release_year = year
            except (TypeError, ValueError):
                pass # Handle cases where timestamp might be invalid

        # Select only the fields you want in Meilisearch
        # Ensure 'id' is present and is the primary key
        doc = {
            'id': game_doc.get('id'), # Must match primaryKey
            'name': game_doc.get('name'),
            'parent_game': game_doc.get('parent_game'), # Will be None if not present
            'version_parent': game_doc.get('version_parent'), # Will be None if not present
            'game_type': game_doc.get('game_type'), # Will be None if not present
            'cover_url': cover_url, # Add constructed cover_url
            'release_year': release_year
        }
        # Ensure 'id' is not None
        if doc['id'] is not None:
             documents_to_add.append(doc)
        else:
            print(f"Skipping game due to missing ID: {str(game_doc)[:100]}")

    
    if documents_to_add:
        try:
            task_info = index.add_documents(documents_to_add, primary_key='id')
            print(f"Meilisearch: Submitted {len(documents_to_add)} documents. Task UID: {task_info.task_uid}")
            # For critical data, you might want to wait for the task:
            # meili_client_instance.wait_for_task(task_info.task_uid)
        except Exception as e:
            print(f"Error adding documents to Meilisearch: {e}")

def get_access_token():
    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    response = requests.post(url, params=params)
    response.raise_for_status()
    data = response.json()
    print("Token expires in (seconds):", data['expires_in'])
    return data['access_token']

def query_igdb(access_token, endpoint, body):
    url = f'https://api.igdb.com/v4/{endpoint}'
    headers = {
        'Client-ID': CLIENT_ID,
        'Authorization': f'Bearer {access_token}'
    }
    # print(f"Querying IGDB: {url} with body: {body[:200]}...") # For debugging
    response = requests.post(url, headers=headers, data=body)
    response.raise_for_status()
    return response.json()

def fetch_and_store_all(access_token, endpoint_path, collection_name, mongo_client, meili_client_instance, fields_to_fetch_string="fields *;", batch_limit=100):
    """
    Fetches all data from a given IGDB endpoint and stores it in a MongoDB collection.
    """
    db = mongo_client[MONGO_DB_NAME]
    collection = db[collection_name]
    # Ensure an index on 'id' for efficient upserts and lookups.
    # `background=True` allows other operations while the index is built.
    try:
        collection.create_index("id", unique=True, background=True)
    except pymongo.errors.OperationFailure as e:
        # Handle cases where index creation might fail if options changed on an existing index
        print(f"Note: Index on 'id' for collection '{collection_name}' might already exist with different options or failed to create: {e}")

    # Delete all existing documents in the collection to overwrite
    print(f"\nDeleting existing data from collection '{collection_name}'...")
    try:
        delete_result = collection.delete_many({})
        print(f"Deleted {delete_result.deleted_count} documents from '{collection_name}'.")
    except Exception as e:
        print(f"Error deleting data from '{collection_name}': {e}. Proceeding with fetch anyway.")

    print(f"Fetching all data for endpoint '{endpoint_path}' into collection '{collection_name}'...")

    # Get total count for the endpoint
    count_body = "fields id;" # IGDB count endpoint needs at least one field specified
    try:
        count_response = query_igdb(access_token, f"{endpoint_path}/count", count_body)
        total_items = count_response['count']
        print(f"Total items in '{endpoint_path}': {total_items}")
        if total_items == 0:
            print(f"No items to fetch for '{endpoint_path}'. Skipping.")
            return
    except Exception as e:
        print(f"Error fetching count for {endpoint_path}: {e}. Skipping this endpoint.")
        return

    offset = 0
    items_processed_count = 0
    
    while offset < total_items:
        # Construct the query body for fetching a batch of items
        query_body = f"{fields_to_fetch_string} limit {batch_limit}; offset {offset}; sort id asc;"
        
        try:
            print(f"Fetching from '{endpoint_path}': offset {offset}, limit {batch_limit}")
            batch_data = query_igdb(access_token, endpoint_path, query_body)
            
            if not batch_data:
                print(f"No items returned for '{endpoint_path}' at offset {offset}. This might be the end or an issue.")
                # If total_items was > 0, this might indicate an issue or end of actual data despite count
                break 

            if endpoint_path == "games" and batch_data: # batch_data contains the list of game dicts
                add_games_to_meilisearch(batch_data, meili_client_instance, db)
            operations = []
            for item_doc in batch_data:
                if 'id' not in item_doc:
                    print(f"Warning: Item found without 'id' in '{endpoint_path}', skipping: {str(item_doc)[:100]}...")
                    continue
                # Prepare for upsert: update if 'id' exists, insert if not.
                operations.append(
                    pymongo.UpdateOne({'id': item_doc['id']}, {'$set': item_doc}, upsert=True)
                )
            
            if operations:
                result = collection.bulk_write(operations)
            
            items_processed_count += len(batch_data)
            print(f"Processed batch of {len(batch_data)} for '{endpoint_path}'. Total processed for this endpoint: {items_processed_count}")
            
            offset += len(batch_data)

            # This condition helps exit if the API returns fewer items than requested,
            # which can happen on the last page.
            if len(batch_data) < batch_limit:
                print(f"Fetched less than limit for '{endpoint_path}', assuming end of data for this endpoint.")
                break
        
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error fetching batch from '{endpoint_path}': {e.response.status_code} - {e.response.text}")
            if e.response.status_code == 429: # Too Many Requests
                print("Rate limit hit. Waiting for 60 seconds...")
                time.sleep(60)
            else:
                # For other HTTP errors, you might want to log and break or implement retries
                print(f"An unrecoverable HTTP error occurred for '{endpoint_path}'. Stopping fetch for this endpoint.")
                break 
        except Exception as e:
            print(f"An unexpected error occurred during batch processing for '{endpoint_path}': {e}")
            # Depending on the error, you might want to retry, skip batch, or stop
            time.sleep(5) # Brief pause before potential next attempt or loop iteration

    print(f"Finished fetching for '{endpoint_path}'. Total items processed and stored: {items_processed_count}")


def main():
    access_token = get_access_token()
    mongo_client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    
    meili_client_instance = None
    try:
        meili_client_instance = meilisearch.Client(MEILI_HOST_URL, MEILI_MASTER_KEY)
        # Basic check to see if Meilisearch is reachable
        setup_meilisearch_index(meili_client_instance)
        
        if not meili_client_instance.is_healthy():
            print("Warning: Meilisearch is connected but reported as not healthy after setup attempt.")
    except Exception as e:
        print(f"Could not connect to Meilisearch: {e}. Proceeding without Meilisearch indexing.")
        meili_client_instance = None # Ensure it's None if connection failed

    try:
        print(f"Connected to MongoDB. Using database: '{MONGO_DB_NAME}'")

        endpoints = [
            # Pick the endpoints you want to fetch
            "age_ratings",
            "age_rating_categories",
            "age_rating_content_descriptions_v2",
            "age_rating_organizations",
            "alternative_names",
            "artworks",
            "characters",
            "character_genders",
            "character_mug_shots",
            "character_species",
            "collections",
            "collection_memberships",
            "collection_membership_types",
            "collection_relations",
            "collection_relation_types",
            "collection_types",
            "companies",
            "company_logos",
            "company_statuses",
            "company_websites",
            "covers",
            "date_formats",
            "event_logos",
            "event_networks",
            "events",
            "external_games",
            "external_game_sources",
            "franchises",
            "games",
            "game_engines",
            "game_engine_logos",
            "game_localizations",
            "game_modes",
            "game_release_formats",
            "game_statuses",
            "game_time_to_beats",
            "game_types",
            "game_versions",
            "game_version_features",
            "game_version_feature_values",
            "game_videos",
            "genres",
            "keywords",
            "involved_companies",
            "languages",
            "language_supports",
            "language_support_types",
            "multiplayer_modes",
            "network_types",
            "platforms",
            "platform_families",
            "platform_logos",
            "platform_types",
            "platform_versions",
            "platform_version_companies",
            "platform_version_release_dates",
            "platform_websites",
            "player_perspectives",
            "popularity_primitives",
            "popularity_types",
            "regions",
            "release_dates",
            "release_date_regions",
            "release_date_statuses",
            "screenshots",
            "themes",
            "websites",
            "website_types"
        ]
        for endpoint in endpoints:
            fetch_and_store_all(access_token, endpoint, endpoint, mongo_client, meili_client_instance, batch_limit=500)

    except Exception as e:
        print(f"An error occurred in the main execution: {e}")
    finally:
        if mongo_client:
            mongo_client.close()
            print("\nMongoDB connection closed.")

if __name__ == '__main__':
    main()