import json

def load_games(filepath="games_output.json"):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def calculate_jaccard_similarity(set1, set2):
    if not set1 and not set2:
        return 1.0 # Both empty, consider them perfectly similar in this context
    if not set1 or not set2:
        return 0.0 # One is empty, the other is not
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union != 0 else 0.0

def recommend_games_jaccard(liked_game_name, all_games, top_n=5, genre_weight=0.4, keyword_weight=0.2, theme_weight=0.4):
    seed_game = None
    for game in all_games:
        if game['name'].lower() == liked_game_name.lower():
            seed_game = game
            break
    
    if not seed_game:
        print(f"Game '{liked_game_name}' not found.")
        return []

    seed_genres = set(seed_game.get('genres', []))
    seed_keywords = set(seed_game.get('keywords', []))
    seed_themes = set(seed_game.get('themes', [])) # Get themes for seed game

    recommendations = []
    for game in all_games:
        if game.get('id') == seed_game.get('id'): # Ensure comparison with seed_game's id
            continue

        current_genres = set(game.get('genres', []))
        current_keywords = set(game.get('keywords', []))
        current_themes = set(game.get('themes', [])) # Get themes for current game

        genre_sim = calculate_jaccard_similarity(seed_genres, current_genres)
        keyword_sim = calculate_jaccard_similarity(seed_keywords, current_keywords)
        theme_sim = calculate_jaccard_similarity(seed_themes, current_themes) # Calculate theme similarity
        
        total_similarity = (genre_weight * genre_sim) + \
                           (keyword_weight * keyword_sim) + \
                           (theme_weight * theme_sim) # Add theme similarity to total
        
        if total_similarity > 0: # Only consider games with some similarity
            recommendations.append({'name': game['name'], 'score': total_similarity, 'id': game.get('id')})

    recommendations.sort(key=lambda x: x['score'], reverse=True)
    return recommendations[:top_n]

# Example Usage (assuming you have games_output.json in the same directory)
if __name__ == "__main__":
    games_data = load_games()
    if games_data:
        # Find a game name from your JSON to test with
        # For example, if "Spectrolite" (id: 176361) is in your JSON
        liked_game = "Elden Ring" # Replace with an actual game from your list
        recommended = recommend_games_jaccard(liked_game, games_data)
        print(f"\nRecommendations based on '{liked_game}':")
        for rec in recommended:
            print(f"- {rec['name']} (Score: {rec['score']:.2f})")

        # Example with a game that might have many shared keywords/genres with others
        # liked_game_rpg = "Some Popular RPG" # Replace with an actual RPG from your list
        # recommended_rpg = recommend_games_jaccard(liked_game_rpg, games_data)
        # print(f"\nRecommendations based on '{liked_game_rpg}':")
        # for rec in recommended_rpg:
        #     print(f"- {rec['name']} (Score: {rec['score']:.2f})")