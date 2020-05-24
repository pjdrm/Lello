import os
import copy
import random
from slack import RTMClient
from slack import WebClient
from slack.errors import SlackApiError

PRESENTER_EMOJI = 'sign_up'
LOTTERY_EMOJI = 'game_die'
CMD_PREFIX = '!'
VALID_CMD_EMOJI = '+1'
LOTTERY_DRAW_EMOJI = 'slot_machine'

MSG_TEMPLATE = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Unbabel arXiv reading group *sign up*\n"+"*Presenters* :"+PRESENTER_EMOJI+":\n\n"+"*Lottery Pool* :"+LOTTERY_EMOJI+":\n\n*Papers:*"
            },
            "accessory": {
                "type": "image",
                "image_url": "https://images.trustinnews.pt/uploads/sites/6/2020/01/110612550.jpg",
                "alt_text": "computer thumbnail"
            }
        }
    ]

class LelloBot:

    def __init__(self, bot_token, read_group_chan, max_presenters=3):
        self.bot_token = bot_token
        self.web_client = WebClient(token=bot_token)
        self.read_group_chan = read_group_chan
        self.max_presenters = max_presenters
        self.presenters = []
        self.lottery = []
        self.papers = {}
        self.announce_msg_ts = None
        self.channel_id = None
        # TODO: add logic to figure out when to trigger sending announcement
        self.send_announcement()

    def get_user_real_name(self, user_id):
        response = self.web_client.users_info(
            user=user_id
        )
        user_real_name = response['user']['real_name']
        return user_real_name

    def send_announcement(self):
        # TODO: pin announcement
        try:
            response = self.web_client.chat_postMessage(
                channel=self.read_group_chan,
                blocks=MSG_TEMPLATE
            )
            self.announce_msg_ts = response['message']['ts']
            self.channel_id = response['channel']
            self.web_client.reactions_add(name=PRESENTER_EMOJI,
                                          channel=self.channel_id,
                                          timestamp=self.announce_msg_ts)
            self.web_client.reactions_add(name=LOTTERY_EMOJI,
                                          channel=self.channel_id,
                                          timestamp=self.announce_msg_ts)
        except SlackApiError as e:
            # You will get a SlackApiError if "ok" is False
            assert e.response["error"]  # str like 'invalid_auth', 'channel_not_found'

    def sign_up(self, chan_id, user_id, reaction_emoji):
        user_presenter = self.get_user_real_name(user_id)
        if reaction_emoji == PRESENTER_EMOJI:
            if user_presenter not in self.presenters:
                self.presenters.append(user_presenter)
                if user_presenter in self.lottery:
                    self.lottery.remove(user_presenter)
        elif reaction_emoji == LOTTERY_EMOJI:
            if user_presenter not in self.lottery:
                self.lottery.append(user_presenter)
                if user_presenter in self.presenters:
                    self.presenters.remove(user_presenter)
                    self.papers.pop(user_presenter, None)

        self.update_announcement(chan_id)

    def lottery_draw(self, chan_id):
        # TODO: make admin only command
        lottery_pool = copy.deepcopy(self.lottery)
        random.shuffle(lottery_pool)
        for draw in lottery_pool:
            if len(self.presenters) == self.max_presenters:
                break
            self.presenters.append(draw)
            self.lottery.remove(draw)

        self.update_announcement(chan_id)

    # TODO: get chan_id in constructor
    def update_announcement(self, chan_id):
        # TODO: Better announcement format if no presenters/lottery sign ups
        update_msg = copy.deepcopy(MSG_TEMPLATE)
        presenters = []
        paper_list = []
        for presenter in self.presenters:
            if presenter in self.papers:
                paper_list.append(self.papers[presenter]['title'])
                presenter = '<'+self.papers[presenter]['url']+'|'+presenter+'>'

            presenters.append(presenter)

        presenters_str = '\n'.join(['\t• '+p for p in presenters])
        lottery_str = '\n'.join(['\t• '+l for l in self.lottery])
        if len(paper_list) > 0:
            papers_str = '\n'.join(['\t• '+p for p in paper_list])
        else:
            papers_str = ''
        update_msg[0]['text']['text'] = "Unbabel arXiv reading group *sign up*\n"+\
                                        "*Presenters* :"+PRESENTER_EMOJI+":\n"+presenters_str+"\n\n"+\
                                        "*Lottery Pool* :"+LOTTERY_EMOJI+":\n"+lottery_str+"\n\n"+\
                                        "*Papers:*\n"+papers_str
        response = lello_bot.web_client.chat_update(
            channel=chan_id,
            ts=self.announce_msg_ts,
            blocks=update_msg
        )

    def add_paper(self, chan_id, paper_title, paper_url, user_id, user_index):
        if user_index is not None:
            user_real_name = self.presenters[user_index]
        else:
            user_real_name = self.get_user_real_name(user_id)
            if user_real_name not in self.presenters:
                # Auto sign-up by adding paper
                self.presenters.append(user_real_name)
                if user_real_name in self.lottery:
                    self.lottery.remove(user_real_name)

        self.papers[user_real_name] = {'title': paper_title, 'url': paper_url}
        self.update_announcement(chan_id)

@RTMClient.run_on(event="reaction_added")
def parse_reaction(**payload):
    reaction_emoji = payload['data']['reaction']
    user_id = payload['data']['user']
    ts = payload['data']['item']['ts']
    channel_id = payload['data']['item']['channel']
    if ts == lello_bot.announce_msg_ts:
        print('Got Reaction')
        if reaction_emoji in [PRESENTER_EMOJI, LOTTERY_EMOJI]:
            lello_bot.sign_up(channel_id, user_id, reaction_emoji)
            # TODO: better reaction clean up (ideally the sign up reaction from bot). But the api does not seem to support remove user reactions
        elif reaction_emoji == LOTTERY_DRAW_EMOJI:
            lello_bot.lottery_draw(channel_id)
    # TODO: remove sign up reaction

@RTMClient.run_on(event="message")
def parse_message(**payload):
    text = payload['data']['text']
    if text.startswith(CMD_PREFIX):
        command = text.split(' ')[0][1:]
        if command == 'paper':
            print('Got paper command')
            # TODO: validate arguments and send message if they are wrong
            text_split = text.split('"')
            paper_title = text_split[1]
            if '\xa0' in text_split[-1]:
                # Seems slack tries to detect URLs and does not send the plain text
                text_split = text_split[-1].split('\xa0')[1:]
                paper_url = text_split[0][:-1].split('|')[1]
            else:
                # In case slack misses that this is a URL
                text_split = text_split[-1].split(' ')
                paper_url = text_split[0]
            user_index = None
            user_id = None
            if len(text_split) == 2:
                user_index = int(text_split[1])
            else:
                user_id = payload['data']['user']

            channel_id = payload['data']['channel']
            ts = payload['data']['ts']
            lello_bot.add_paper(channel_id, paper_title, paper_url, user_id, user_index)
            lello_bot.web_client.reactions_add(name=VALID_CMD_EMOJI,
                                               channel=channel_id,
                                               timestamp=ts)
            # TODO: delete command messsage
        # TODO: admin command to add people
        # TODO: admin command to remove people

if __name__ == "__main__":
    slack_token = os.environ["SLACK_API_TOKEN"]
    read_group_chan = 'bot'
    lello_bot = LelloBot(slack_token, read_group_chan)
    rtm_client = RTMClient(
        token=slack_token,
        connect_method='rtm.start'
    )
    print('Bot ready')
    rtm_client.start()
