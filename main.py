import os
import requests
import json # query_igdb returns JSON, but json module might not be directly used in main
import pymongo # For MongoDB interaction
import time

# Replace these with your actual Client ID and Client Secret
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

# --- MongoDB Connection Details ---
MONGO_CONNECTION_STRING = "mongodb://localhost:27017/" # Default local MongoDB
MONGO_DB_NAME = "igdb_data"
# Collection names will be 'games', 'age_ratings', 'age_rating_content_descriptions_v2'
# --- ---

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

def fetch_and_store_all(access_token, endpoint_path, collection_name, mongo_client, fields_to_fetch_string="fields *;", batch_limit=100):
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
                # Optional: More detailed logging of bulk_write results
                # print(f"MongoDB ({collection_name}): Matched {result.matched_count}, Upserted {result.upserted_count}, Modified {result.modified_count} docs.")
            
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
    
    try:
        print(f"Connected to MongoDB. Using database: '{MONGO_DB_NAME}'")

        endpoints = [
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
            fetch_and_store_all(access_token, endpoint, endpoint, mongo_client, batch_limit=500)

    except Exception as e:
        print(f"An error occurred in the main execution: {e}")
    finally:
        if mongo_client:
            mongo_client.close()
            print("\nMongoDB connection closed.")

if __name__ == '__main__':
    main()