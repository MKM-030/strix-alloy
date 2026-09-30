import random
WORDS = 'the river bends past a quiet town where old mills once ground wheat for every family along the valley and children still climb the stone bridge to watch boats carry timber salt and wool toward distant markets while farmers mend fences count sheep and argue about rain clouds that gather over the western hills each autumn evening before the harvest festival brings music lanterns and long tables of bread cheese apples and cider shared by neighbours who remember older winters when snow closed the road for weeks and stories were traded by firelight instead of coins'.split()

def synthetic_text(seed: int, words: int) -> str:
    """Deterministic prose-like text with a fixed vocabulary."""
    rng = random.Random(seed)
    out: list[str] = []
    count = 0
    while count < words:
        sentence_len = min(rng.randint(6, 14), words - count)
        sentence = [rng.choice(WORDS) for _ in range(sentence_len)]
        sentence[0] = sentence[0].capitalize()
        out.append(' '.join(sentence) + '.')
        count += sentence_len
        if rng.random() < 0.2:
            out.append('\n\n')
    return ' '.join(out).replace(' \n\n ', '\n\n').strip()
TASKS = {'prose': '\n\nSummarize the passage above in detail, then write a short story inspired by it. Write at least 500 words.', 'repetition': '\n\nRepeat the passage above word for word, from the beginning.', 'copy': '\n\nCopy ONLY the passage in this message verbatim. Start with its first word, preserve every word and punctuation mark, and continue until the complete passage has been copied. Do not comment, summarize, or use ellipses.', 'story': '\n\nUse the passage only as inspiration for an original story about a river town. Do not analyze or summarize the passage. Begin the story immediately and write at least 1000 words, with detailed scenes, dialogue, and a developing plot.', 'thinking': '\n\nHow many distinct words appear in the passage above, and which three are the most frequent? Work through it carefully before answering.'}
