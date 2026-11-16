import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib

# Fine-grained personal access token or standard token with permissions:
# Account permissions: read:Followers, read:Starring, read:Watching
# Repository permissions: read:Commit statuses, read:Contents, read:Metadata
HEADERS = {'authorization': 'token ' + os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']
QUERY_COUNT = {
    'user_getter': 0,
    'follower_getter': 0,
    'stars_getter': 0,
    'public_repos_getter': 0,
    'contributions_and_repos': 0,
    'recursive_loc': 0,
    'loc_query': 0,
}


def daily_readme(birthday):
    """
    Returns the length of time since I was born
    e.g. 'XX years, XX months, XX days'
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years),
        diff.months, 'month' + format_plural(diff.months),
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '')


def format_plural(unit):
    return 's' if unit != 1 else ''


def simple_request(func_name, query, variables):
    """
    Returns a request, or raises an Exception if the response does not succeed.
    """
    request = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=HEADERS,
    )
    if request.status_code == 200:
        return request
    raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)


def user_getter(username):
    """
    Returns the account ID and creation time of the user
    """
    query_count('user_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    request = simple_request(user_getter.__name__, query, {'login': username})
    user_data = request.json()['data']['user']
    return {'id': user_data['id']}, user_data['createdAt']


def follower_getter(username):
    """
    Returns the number of followers of the user
    """
    query_count('follower_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def stars_getter(username):
    """
    Returns the total number of starred repositories (matches the Stars tab on GitHub profile)
    """
    query_count('stars_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            starredRepositories {
                totalCount
            }
        }
    }'''
    request = simple_request(stars_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['starredRepositories']['totalCount'])


def public_repos_getter(username):
    """
    Returns the count of public, non-fork repositories owned by the user (matches profile view)
    """
    query_count('public_repos_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            repositories(privacy: PUBLIC, isFork: false, ownerAffiliations: [OWNER]) {
                totalCount
            }
        }
    }'''
    request = simple_request(public_repos_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['repositories']['totalCount'])


def contributions_and_repos(username, created_at_str):
    """
    Queries GitHub's GraphQL API for all-time contributions and unique repos contributed to
    from the account creation year to the current year.
    """
    query_count('contributions_and_repos')
    created_year = int(created_at_str[:4])
    current_year = datetime.datetime.now().year

    total_contributions = 0
    contributed_repo_set = set()

    for year in range(created_year, current_year + 1):
        start_date = f'{year}-01-01T00:00:00Z'
        end_date = f'{year}-12-31T23:59:59Z'
        query = '''
        query($login: String!, $from: DateTime!, $to: DateTime!) {
            user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                    contributionCalendar {
                        totalContributions
                    }
                    commitContributionsByRepository(maxRepositories: 100) {
                        repository {
                            nameWithOwner
                        }
                    }
                }
            }
        }'''
        variables = {'login': username, 'from': start_date, 'to': end_date}
        res = simple_request(contributions_and_repos.__name__, query, variables).json()
        col = res['data']['user']['contributionsCollection']
        total_contributions += col['contributionCalendar']['totalContributions']
        for item in col.get('commitContributionsByRepository', []):
            if item.get('repository'):
                contributed_repo_set.add(item['repository']['nameWithOwner'])

    return total_contributions, max(len(contributed_repo_set), 1)


def recursive_loc(owner, repo_name, data, cache_comment, addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    """
    Uses GitHub's GraphQL v4 API and cursor pagination to fetch commits from a repository
    """
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    request = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=HEADERS,
    )
    if request.status_code == 200:
        repo_data = request.json().get('data', {}).get('repository')
        if repo_data and repo_data.get('defaultBranchRef'):
            history = repo_data['defaultBranchRef']['target']['history']
            for node in history['edges']:
                author_user = node['node'].get('author', {}).get('user')
                if author_user and author_user == OWNER_ID:
                    my_commits += 1
                    addition_total += node['node']['additions']
                    deletion_total += node['node']['deletions']

            if not history['pageInfo']['hasNextPage']:
                return addition_total, deletion_total, my_commits
            return recursive_loc(owner, repo_name, data, cache_comment, addition_total, deletion_total, my_commits, history['pageInfo']['endCursor'])
        return addition_total, deletion_total, my_commits

    force_close_file(data, cache_comment)
    if request.status_code == 403:
        raise Exception('Too many requests in a short amount of time!\nYou\'ve hit the non-documented anti-abuse limit!')
    raise Exception('recursive_loc() has failed with a', request.status_code, request.text, QUERY_COUNT)


def loc_query(comment_size=0, force_cache=False, cursor=None, edges=[]):
    """
    Queries public, non-fork repositories owned by the user to calculate accurate lines of code.
    """
    query_count('loc_query')
    query = '''
    query ($login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, privacy: PUBLIC, isFork: false, ownerAffiliations: [OWNER]) {
                edges {
                    node {
                        nameWithOwner
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    page_data = request.json()['data']['user']['repositories']
    edges = edges + page_data['edges']
    if page_data['pageInfo']['hasNextPage']:
        return loc_query(comment_size, force_cache, page_data['pageInfo']['endCursor'], edges)
    return cache_builder(edges, comment_size, force_cache)


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    cached = True
    os.makedirs('cache', exist_ok=True)
    filename = 'cache/' + hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt'
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError:
        data = []
        if comment_size > 0:
            for _ in range(comment_size):
                data.append('This line is a comment block. Write whatever you want here.\n')
        with open(filename, 'w') as f:
            f.writelines(data)

    if len(data) - comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f:
            data = f.readlines()

    cache_comment = data[:comment_size]
    data = data[comment_size:]
    for index in range(len(edges)):
        parts = data[index].split()
        repo_hash = parts[0]
        commit_count = parts[1]
        target_ref = edges[index]['node'].get('defaultBranchRef')
        total_branch_commits = target_ref['target']['history']['totalCount'] if target_ref else 0
        if repo_hash == hashlib.sha256(edges[index]['node']['nameWithOwner'].encode('utf-8')).hexdigest():
            if int(commit_count) != total_branch_commits:
                owner, repo_name = edges[index]['node']['nameWithOwner'].split('/')
                loc = recursive_loc(owner, repo_name, data, cache_comment)
                data[index] = f"{repo_hash} {total_branch_commits} {loc[2]} {loc[0]} {loc[1]}\n"

    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges, filename, comment_size):
    with open(filename, 'r') as f:
        data = []
        if comment_size > 0:
            data = f.readlines()[:comment_size]
    with open(filename, 'w') as f:
        f.writelines(data)
        for node in edges:
            f.write(hashlib.sha256(node['node']['nameWithOwner'].encode('utf-8')).hexdigest() + ' 0 0 0 0\n')


def force_close_file(data, cache_comment):
    os.makedirs('cache', exist_ok=True)
    filename = 'cache/' + hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)


def svg_overwrite(filename, age_data, commit_data, star_data, repo_data, contrib_data, follower_data, loc_data):
    """
    Parse SVG files and update elements with age, commits, stars, repositories, and lines written.
    Also fixes the spelling typo 'Commmits' -> 'Commits'.
    """
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix typo 'Commmits' -> 'Commits' if present
    content = content.replace('>Commmits<', '>Commits<')

    tree = etree.fromstring(content.encode('utf-8'))
    justify_format(tree, 'age_data', age_data, 49)
    justify_format(tree, 'commit_data', commit_data, 22)
    justify_format(tree, 'star_data', star_data, 14)
    justify_format(tree, 'repo_data', repo_data, 6)
    justify_format(tree, 'contrib_data', contrib_data)
    justify_format(tree, 'follower_data', follower_data, 10)
    justify_format(tree, 'loc_data', loc_data[2], 9)
    justify_format(tree, 'loc_add', loc_data[0])
    justify_format(tree, 'loc_del', loc_data[1], 7)

    xml_str = etree.tostring(tree, encoding='utf-8', xml_declaration=True).decode('utf-8')
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(xml_str)


def justify_format(root, element_id, new_text, length=0):
    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)
    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: '', 1: ' ', 2: '. '}
        dot_string = dot_map[just_len]
    else:
        dot_string = ' ' + ('.' * just_len) + ' '
    find_and_replace(root, f"{element_id}_dots", dot_string)


def find_and_replace(root, element_id, new_text):
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def query_count(funct_id):
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1


if __name__ == '__main__':
    """
    Aarti Seth (4artiseth) Profile Stats Generator
    Dynamically computes real, accurate GitHub statistics
    """
    user_data = user_getter(USER_NAME)
    OWNER_ID, acc_date = user_data

    # Age calculation: Born 24 January 2005
    age_data = daily_readme(datetime.datetime(2005, 1, 24))

    # All-time contributions and unique repos contributed to from the contributions calendar
    commit_data, contrib_data = contributions_and_repos(USER_NAME, acc_date)

    # Public repositories count
    repo_data = public_repos_getter(USER_NAME)

    # Starred repositories count (matches the profile's Stars tab)
    star_data = stars_getter(USER_NAME)

    # Followers count
    follower_data = follower_getter(USER_NAME)

    # Accurate Lines of Code (public, non-fork repositories)
    total_loc = loc_query(7)
    formatted_loc = ['{:,}'.format(x) for x in total_loc[:-1]]

    # Update both SVG files
    svg_overwrite('dark_mode.svg', age_data, commit_data, star_data, repo_data, contrib_data, follower_data, formatted_loc)
    svg_overwrite('light_mode.svg', age_data, commit_data, star_data, repo_data, contrib_data, follower_data, formatted_loc)

    print('Updated successfully with accurate stats:')
    print(f'  Age: {age_data}')
    print(f'  Repos: {repo_data} {{Contributed: {contrib_data}}}')
    print(f'  Stars: {star_data}')
    print(f'  Commits: {commit_data}')
    print(f'  Followers: {follower_data}')
    print(f'  Lines of Code: {formatted_loc[2]} ({formatted_loc[0]}++, {formatted_loc[1]}--)')
