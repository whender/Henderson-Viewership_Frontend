"""Verified AP releases used while the archive feed catches up."""

def merge_updates(polls, votes, updates):
    polls = list(polls)
    for update in updates:
        poll = update['poll']
        matches = [p for p in polls if p['season'] == poll['season'] and p.get('releaseDate') == poll['releaseDate']]
        canonical = next((p for p in matches if not p.get('provisionalId')), None)
        if canonical:
            polls = [p for p in polls if p not in matches or p is canonical]
            votes.setdefault(str(canonical['id']), update['votes'])
        elif not matches:
            polls.append(poll)
            votes[str(poll['id'])] = update['votes']
    return sorted(polls, key=lambda p:p['id']), votes
