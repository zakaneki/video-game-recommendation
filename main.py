import os
import requests
import json

# Replace these with your actual Client ID and Client Secret
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

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
    response = requests.post(url, headers=headers, data=body)
    response.raise_for_status()
    return response.json()

def get_names_from_ids(ids, endpoint, access_token):
    # Fetch names for list of IDs
    url = f'https://api.igdb.com/v4/{endpoint}'
    headers = {
        'Client-ID': CLIENT_ID,
        'Authorization': f'Bearer {access_token}'
    }
    ids_str = ', '.join(str(i) for i in ids)
    body = f'fields name; where id = ({ids_str});'
    resp = requests.post(url, headers=headers, data=body)
    resp.raise_for_status()
    return [item['name'] for item in resp.json()]

def get_id_name_map_batched(ids_list, endpoint, access_token, batch_size=500):
    id_to_name_map = {}
    if not ids_list:
        return id_to_name_map

    print(f"Fetching names for {len(ids_list)} unique IDs from '{endpoint}' endpoint...")
    for i in range(0, len(ids_list), batch_size):
        current_batch_ids = ids_list[i:i+batch_size]
        ids_str = ','.join(map(str, current_batch_ids))
        
        body = f'fields id, name; where id = ({ids_str}); limit {len(current_batch_ids)};'
        
        url = f'https://api.igdb.com/v4/{endpoint}'
        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {access_token}'
        }
        
        try:
            response = requests.post(url, headers=headers, data=body)
            response.raise_for_status()
            results = response.json()
            for item in results:
                id_to_name_map[item['id']] = item['name']
            # Optional: Add a small delay if making many batch requests
            # if len(ids_list) > batch_size and (i + batch_size) < len(ids_list):
            #     time.sleep(0.25) 
        except requests.exceptions.RequestException as e:
            print(f"Error fetching batch from {endpoint} for some IDs: {e}")
        except Exception as e:
            print(f"An unexpected error occurred processing batch from {endpoint}: {e}")

    print(f"Successfully mapped {len(id_to_name_map)} out of {len(ids_list)} IDs from '{endpoint}'.")
    return id_to_name_map

def main():
    access_token = get_access_token()

    # Get total number of games
    count_response = query_igdb(access_token, 'games/count', "") # Body can be empty for count
    total_games = count_response['count']
    print(f"Total games available: {total_games}")

    all_games_data = []
    limit = 500  # Maximum limit per request
    offset = 0

    print("Fetching all games...")
    while offset < total_games:
        body_games = f'''
            fields id, name, genres, keywords, themes;
            limit {limit};
            offset {offset};
        '''
        print(f"Fetching games: offset {offset}, limit {limit}")
        batch_games = query_igdb(access_token, 'games', body_games)
        
        if not batch_games:
            print("No more games returned from API, stopping.")
            break
        
        all_games_data.extend(batch_games)
        offset += len(batch_games) # Increment offset by the number of games actually fetched

        # Optional: Add a small delay to be respectful to the API rate limits
        # time.sleep(0.25) # 250ms delay between requests

        # Break if we fetched less than limit, implying it was the last page
        if len(batch_games) < limit:
            break
            
    print(f"Fetched {len(all_games_data)} games in total.")

    # Collect all unique genre and keyword IDs
    all_unique_genre_ids = set()
    all_unique_keyword_ids = set()
    all_unique_theme_ids = set() # Add set for theme IDs
    print("Collecting unique genre and keyword IDs from all fetched games...")
    for game_item in all_games_data:
        if 'genres' in game_item:
            all_unique_genre_ids.update(game_item['genres'])
        if 'keywords' in game_item:
            all_unique_keyword_ids.update(game_item['keywords'])
        if 'themes' in game_item: # Collect theme IDs
            all_unique_theme_ids.update(game_item['themes'])
    
        print(f"Found {len(all_unique_genre_ids)} unique genre IDs, {len(all_unique_keyword_ids)} unique keyword IDs, and {len(all_unique_theme_ids)} unique theme IDs.")
    # Batch fetch names for all unique IDs
    genre_id_to_name = {}
    if all_unique_genre_ids:
        genre_id_to_name = get_id_name_map_batched(list(all_unique_genre_ids), 'genres', access_token)

    keyword_id_to_name = {}
    if all_unique_keyword_ids:
        keyword_id_to_name = get_id_name_map_batched(list(all_unique_keyword_ids), 'keywords', access_token)

    theme_id_to_name = {} # Add map for theme IDs to names
    if all_unique_theme_ids: # Fetch theme names
        theme_id_to_name = get_id_name_map_batched(list(all_unique_theme_ids), 'themes', access_token)

    # Prepare data for JSON output
    output_games_list = []
    print(f"Preparing game data for JSON output...")
    for game in all_games_data:
        name = game['name']
        game_id = game.get('id') # Good to keep the ID
        genre_ids_for_game = game.get('genres', [])
        keyword_ids_for_game = game.get('keywords', [])
        theme_ids_for_game = game.get('themes', []) # Get theme IDs for the game
        
        genres = [genre_id_to_name.get(gid) for gid in genre_ids_for_game if genre_id_to_name.get(gid) is not None]
        
        keywords = [keyword_id_to_name.get(kid) for kid in keyword_ids_for_game if keyword_id_to_name.get(kid) is not None]
        
        themes = [theme_id_to_name.get(tid) for tid in theme_ids_for_game if theme_id_to_name.get(tid) is not None] # Get theme names

        output_games_list.append({
            'id': game_id,
            'name': name,
            'genres': genres,
            'keywords': keywords,
            'themes': themes # Add themes to output
        })

    # Save to a JSON file
    output_filename = "games_output.json" # Change to .json
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(output_games_list, f, ensure_ascii=False, indent=4) # Use json.dump
    
    print(f"All game data saved to {output_filename}")

if __name__ == '__main__':
    main()