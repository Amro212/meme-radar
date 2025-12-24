# Hashtag Whitelist Configuration
# Videos containing these hashtags will be automatically flagged for review
# regardless of their velocity/acceleration metrics

# Meme-related hashtags
MEME_HASHTAGS = [
    "meme",
    "memes",
    "dankmemes",
    "memesdaily",
    "funnymemes",
    "relatable",
    "viral",
    "trending",
]

# Animal/Pet hashtags (often meme content)
ANIMAL_HASHTAGS = [
    "cat",
    "cats",
    "catsoftiktok",
    "dog",
    "dogs",
    "dogsoftiktok",
    "animal",
    "animals",
    "pets",
    "funny",
    "funnyanimals",
]

# Slang/Culture hashtags
CULTURE_HASHTAGS = [
    "bro",
    "bruh",
    "lol",
    "lmao",
    "pov",
    "mood",
    "vibe",
    "chaotic",
    "unhinged",
    "cursed",
]

# Reaction/Format hashtags
REACTION_HASHTAGS = [
    "reaction",
    "storytime",
    "rant",
    "comedy",
    "skit",
    "parody",
]

# Compile all whitelisted hashtags (lowercase for matching)
WHITELISTED_HASHTAGS = set([
    tag.lower() for tag in 
    MEME_HASHTAGS + ANIMAL_HASHTAGS + CULTURE_HASHTAGS + REACTION_HASHTAGS
])
