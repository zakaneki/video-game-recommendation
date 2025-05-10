import os
import requests

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

def main():
    access_token = get_access_token()

    # Fetch first 10 games
    body_games = '''
        fields id, name, genres, keywords;
        limit 10;
    '''
    games = query_igdb(access_token, 'games', body_games)

    for game in games:
        name = game['name']
        genre_ids = game.get('genres', [])
        keyword_ids = game.get('keywords', [])
        # Get genre names
        genres = get_names_from_ids(genre_ids, 'genres', access_token) if genre_ids else []
        # Get keyword names
        keywords = get_names_from_ids(keyword_ids, 'keywords', access_token) if keyword_ids else []

        print(f"Game: {name}")
        print(f"  Genres: {', '.join(genres) if genres else 'N/A'}")
        print(f"  Keywords: {', '.join(keywords) if keywords else 'N/A'}")
        print("-" * 40)

if __name__ == '__main__':
    main()