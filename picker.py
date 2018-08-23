import praw
import steam
import configparser
import random
import prawcore
import os
from urllib.parse import urlparse
from bs4 import BeautifulSoup as Soup
from multiprocessing import Pool


class Steam:
    # TODO: handle /profiles/{non-numeric}
    # TODO: throw an exception if an url is invalid.
    # TODO: fix invalid url with /profiles
    def get_id(self, url):
        url = url.strip('/')
        path = urlparse(url).path.strip('/').split('/')
        if path[0] == 'profiles':
            return path[1]
        response = self.resolve_vanity_url(path[1])
        if response['success'] == 1:
            return response['steamid']
        return None

    def resolve_vanity_url(self, url):
        return self.api.call('ISteamUser.ResolveVanityURL', vanityurl=url)['response']

    def get_hidden(self, users):
        ids = []
        for user, data in users:
            ids.append(data['steam_id'])
        response = self.api.call('ISteamUser.GetPlayerSummaries', steamids=','.join(ids))['response']['players']
        hidden = []
        for player in response:
            if not self.is_profile_visible(player['communityvisibilitystate']):
                hidden.append(player['steamid'])
        return hidden

    def is_profile_visible(self, state):
        return state == 3

    def get_level(self, steam_id):
        return self.api.call('IPlayerService.GetSteamLevel', steamid=steam_id)['response']['player_level']

    def is_steam_url(self, url):
        return url.find(self.steam_url) != -1

    def is_level_valid(self, level):
        return level >= self.min_level

    def __init__(self, settings):
        self.api = steam.WebAPI(settings['api_key'])
        self.steam_url = settings['url']
        self.min_level = settings['min_level'].getint()


class Reddit:
    api = praw.Reddit('picker')

    def get_steam_profile(self, comment):
        for a in Soup(comment.body_html, 'html.parser')('a'):
            url = a.get('href')
            if self.steam_api.is_steam_url(url):
                return {'url': url}
        return {}

    def get_karma(self, user):
        return self.api.redditor(user).comment_karma

    def get_submission(self, url):
        return self.api.submission(url=url)

    def is_karma_valid(self, karma):
        return karma >= self.min_karma

    def get_recent_comments(self, limit):
        return self.subreddit.comments(limit=limit)

    @staticmethod
    def has_tag(self, comment, tag):
        return tag in comment.body

    @staticmethod
    def is_user_special(username):
        return username.find('_bot') != -1 or username == 'AutoModerator'

    def __init__(self, steam, settings):
        self.steam_api = steam
        self.min_karma = settings['min_karma'].getint()
        self.subreddit = self.api.subreddit(settings['subreddit'])


class Picker:
    settings = configparser.ConfigParser()
    settings.read('settings.ini')
    eligible = {}
    violators = []
    steam = Steam(settings['steam'])
    reddit = Reddit(steam, settings['reddit'])
    submissions = []
    tag = settings['reddit']['tag']

    def scrap_comments(self, submission):
        try:
            comments = submission.comments
        except prawcore.exceptions.NotFound:
            exit(1)
        for comment in comments:
            username = comment.author.name
            if self.reddit.is_user_special(username):
                continue
            profile = self.reddit.get_steam_profile(comment)
            if profile:
                self.eligible[username] = profile
            else:
                self.violators.append(username)

    def remove_hidden(self):
        hidden = self.steam.get_hidden(self.eligible.items())
        for user, data in self.eligible.copy().items():
            if data['steam_id'] in hidden:
                del self.eligible[user]
                self.violators.append(user)

    def pick(self):
        self.get_drawings(self.settings['reddit']['limit'].getint())
        for item in self.submissions:
            self.draw(item['submission'])
            self.post_results(item['comment'])
            self.eligible = {}
            self.violators = []

    def post_results(self, comment):
        comment.reply(self.get_results())

    def get_results(self):
        results = []
        if self.violators:
            results.append('Users that violate rules: ' + ', '.join(self.violators) + '.\n')
        if self.eligible:
            results.append('Users eligible for drawing: ' + ', '.join(self.eligible.keys()) + '.\n')
            results.append('Winner: ' + self.get_random_user())
        if results:
            results = ['\n\nResults:\n'] + results
        else:
            results.append('No eligible users.')
        return ''.join(results)

    def get_drawings(self, limit):
        for comment in self.reddit.get_recent_comments(limit):
            if not self.replied_to.contains(comment.name) and self.reddit.has_tag(comment, self.tag):
                self.submissions.append({'comment': comment, 'submission': comment.submission})

    def draw(self, submission):
        self.scrap_comments(self.reddit.get_submission(submission))
        self.apply_filter_lists(self.eligible)

        for user in self.eligible.copy():
            url = self.eligible[user].pop('url')
            self.eligible[user]['steam_id'] = self.pool.apply_async(self.steam.get_id, [url])
            self.eligible[user]['karma'] = self.pool.apply_async(self.reddit.get_karma, [user])
        for user, data in self.eligible.copy().items():
            steam_id = data['steam_id'].get()
            if steam_id:
                self.eligible[user]['steam_id'] = steam_id
            else:
                self.eligible.pop(user)
                self.violators.append(user)
        self.remove_hidden()
        for user in self.eligible.copy():
            # TODO: handle HTTP 500 error
            self.eligible[user]['level'] = self.pool.apply_async(self.steam.get_level, [self.eligible[user]['steam_id']])

        for user in self.eligible.copy():
            level = self.eligible[user]['level'].get()
            karma = self.eligible[user]['karma'].get()
            if not (self.steam.is_level_valid(level) and self.reddit.is_karma_valid(karma)):
                self.eligible.pop(user)
                self.violators.append(user)

    def get_random_user(self):
        return random.choice(list(self.eligible))

    def include_users(self, users: dict, to_filter):
        self._filter_users(users, self._include_user, to_filter)

    def _filter_users(self, users: dict, meets_criteria, to_filter):
        for user in users.copy():
            if meets_criteria(user, to_filter):
                users.pop(user)

    def _include_user(self, user, to_filter):
        return not to_filter.contains(user)

    def _exclude_user(self, user, to_filter):
        return to_filter.contains(user)

    def exclude_users(self, users: dict, to_filter):
        self._filter_users(users, self._exclude_user, to_filter)

    def apply_filter_lists(self, users):
        to_include = File(self.settings['general']['included_users'])
        if not to_include.contents():
            to_exclude = File(self.settings['general']['excluded_users'])
            self.exclude_users(users, to_exclude)
            to_exclude.close()
        else:
            self.include_users(users, to_include)
        to_include.close()

    def __init__(self):
        self.replied_to = File(self.settings['general']['replied_to'])
        self.pool = Pool()


class File:
    def __init__(self, file_name):
        self.file_name = file_name
        if os.path.isfile(file_name):
            with open(file_name) as f:
                self.lines = list(filter(None, f.read().split('\n')))
        else:
            self.lines = []
        self.file = open(file_name, 'a')

    def contains(self, line):
        return line in self.lines

    def add_line(self, line):
        self.lines.append(line)
        self.file.write(line)

    def close(self):
        self.file.close()

    def contents(self):
        return self.lines


if __name__ == "__main__":
    Picker().pick()
