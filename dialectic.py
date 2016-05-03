from util import hook, timesince
import collections
import datetime
import time
import re


# variables to tweak bot
interval = 1 # how often the heartbeat checks statuses


#initializing global variables
dsc = False # state variable for dialectic (True = active, False = inactive)
trn = False # state variable for turns (True = someone has the floor, False = no one has the floor)
queue_list = [] # current queue_list of people waiting to speak
queued_list = [] # blacklist: people who have already spoken. it empties when the queue_list is empty. prevents domination of dialectic
turn_length = 60 # length of time someone has the floor
turn_mark = datetime.datetime.utcnow() # placeholder, global
speaker = "" # placeholder, global
awards = collections.defaultdict(collections.Counter)
num_turns = collections.Counter()

# bot needs: 
# some way to get op/admin (can just register nick on server if need be)
# points system (set categories? custom ones? both?)



@hook.command 
def dialectic(inp, conn=None, say=None, nick="", chan="", reply=None):

    """
    Begins a dialectic session.
    Syntax: !dialectic [turn length in seconds] [topic]
    """

    global dsc
    global trn
    global queue_list
    global queued_list
    global turn_length

    if nick=="rawkies" or nick=="gnostikoi": # handlers of Zeno

        if dsc: # can't start a dialectic if it's already going
            reply("A dialectic is already in session.")

        else: # if dialectic is not currently happening...
            parse = inp.split()
            try:
                turn_length = int(parse[0])
                topic = " ".join(parse[1:])
                dsc = True # DIALECTIC: ENGAGE
                trn = False
                conn.cmd('TOPIC', [chan, topic]) # add topic from command
                conn.cmd('MODE '+chan+' +m') # change channel mode to 'moderated'
                say("Welcome to the dialectic... queue is now open. When queueing, be sure to send me a private message, as you are muted in the channel.")
            except ValueError:
                reply("To start a session please use the syntax: !dialectic [turn length in seconds] [topic]")


    else:
        reply("You must be my handler to begin a dialectic.") # deny access for plebs


@hook.command
def end(inp, conn=None, say=None, nick="", chan=""):

    """
    Ends a dialectic session.
    Syntax: !end
    Note: will only work in PM unless user can override voice (e.g. as op)
    """

    global dsc
    global trn
    global speaker

    if nick=="rawkies" or nick=="gnostikoi": # handlers of Zeno
        dsc = False # reset everything to baseline
        trn = False
        queue_list = []
        queued_list = []
        conn.cmd('MODE '+chan+' -v '+speaker)
        conn.cmd('MODE '+chan+' -m')
        say("Thanks to everyone for participating in this dialectic session!")
        
    else:
        reply("You must be my handler to end a dialectic.") # no plebs are allowed to ragequit the dialectic session


@hook.command
def queue(inp, notice=None, reply=None, nick=""):

    """
    Enters the sender into the speaking queue.
    Syntax: !queue
    Note: will only work in PM
    """

    global dsc
    global queue_list
    global queued_list
    global num_turns

    if dsc:

        if nick in queued_list: # if you've already been blacklisted...
            reply("The queue has not yet emptied. You have not been re-added to the queue.") # nothing happens and you have to wait until the queue_list is empty

        else:
            queue_list.append(nick) # add to queue_list
            queued_list.append(nick) # add to blacklist for when person is eventually removed from queue_list
            num_turns[nick] += 1  # add one to the turn counter for queued_list person
            turns_per_person = [num_turns[nick] for nick in queue_list]  # get turn count for each person in queue_list
            queue_list = [x for y,x in sorted(turns_per_person, queue_list)]  # sort 'queue_list' by turn count
            reply("You have been added to the queue.")

    else:

        reply("A dialectic is not in session.")

@hook.command
def whosup(inp, reply=None):

    """
    Replies with the queue.
    Syntax: !whosup
    """

    global queue_list

    if dsc:

        if len(queue_list)==0:
            reply("The queue is empty! If you'd like, add yourself with !queue")

        else:
            out_intro = "Coming up on #dialectics! "
            out_list = []
            for i in range(len(queue_list)):
                out_list.append("{}) {}".format(i+1, queue_list[i]))  # give members of queue_list and number them
            print(out_intro + ", ".join(out_list))  # print full string, separated by commas

    else:

        reply("A dialectic is not in session.")


@hook.command
def award(inp):
    """
    Awards points to user for given reason.
    Syntax: !award [user] [point category]
    """

    global speaker
    global awards

    recv = inp.split()
    awardee = recv[0]
    points = "".join(recv[1:])
    if len(recv)>2 or len(points)!=6:
        reply("Please fix your formatting. Syntax is !award [user] [a(+|.|-)i(+|.|-)l(+|.|-)]. '+' indicates one point is awarded to the user, '.' is no points, and '-' indicates one point is deducted.")
    else:
        categories = ["Accuracy", "Insight", "Logic"]
        scores = {"+": 1, ".": 0, "-": -1}
        if nick==awardee:
            reply("You're not allowed to award points to yourself.")
        else:
            for c in categories:
                awards[c][nick] += scores[re.search("(?<={})(\+|\.|\-)".format(c[0].lower()), points).group(0)]  # gets the score for each category


@hook.singlethread # keeps running in the same thread so as not to spawn a bunch of while loops running simultaneously
@hook.regex(".") # triggers on every line sent from the channel
def heartbeat(inp, conn=None, say=None, chan="", raw=None):

    """
    Controls the flow of a dialectic session.
    """

    global dsc
    global trn
    global queue_list
    global queued_list
    global speaker
    global turn_length
    global turn_mark

    print(raw)

    while dsc: # only loop if a dialectic session is in progress

        if trn: # if someone has the floor...

            if (datetime.datetime.utcnow()-turn_mark).seconds>turn_length: # if someone's turn is over...

                try:
                    conn.cmd('MODE '+chan+' -v '+speaker) # take them off the floor
                    say(speaker+"'s turn has expired.")
                    speaker = queue_list.pop(0) # pull the next person from queue_list. if queue_list is empty, throws IndexError
                    say(speaker+" has the floor.") # mention what happened
                    conn.cmd('MODE '+chan+' +v '+speaker) # give the next person the floor
                    turn_mark = datetime.datetime.utcnow() # mark the beginning of their turn

                except IndexError: # if queue_list is empty, this exception triggers when we try to get the next speaker
                    queued_list = [] # empty the blacklist
                    trn = False # set state so loop starts checking when queue_list is populated again
                    say("The queue is now empty. You are free to enter the queue again.")

        else: # if no one has the floor...

            if len(queue_list)!=0: # if someone entered the queue_list in the last interval...
                trn = True # someone has the floor now
                speaker = queue_list.pop(0) # get the name of the first person in the queue_list
                conn.cmd('MODE '+chan+' +v '+speaker) # give them voice
                say(speaker+" now has the floor.")
                turn_mark = datetime.datetime.utcnow() # mark beginning of turn

        time.sleep(interval) # only loop every *interval* seconds