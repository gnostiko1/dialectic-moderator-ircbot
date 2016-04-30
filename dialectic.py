from util import hook, timesince
import datetime
import time


# variables to tweak bot
interval = 1 # how often the heartbeat checks statuses
turn_length = 60 # length of time someone has the floor


#initializing global variables
dsc = False # state variable for dialectic (True = active, False = inactive)
trn = False # state variable for turns (True = someone has the floor, False = no one has the floor)
queue = [] # current queue of people waiting to speak
queued = [] # blacklist: people who have already spoken. it empties when the queue is empty. prevents domination of dialectic
turn_mark = datetime.datetime.utcnow() # placeholder, global
speaker = "" # placeholder, global


# bot needs: 
# some way to get op/admin (can just register nick on server if need be)
# ability to display queue to user
# points system (set categories? custom ones? both?)


@hook.command 
def dialectic(inp, conn=None, say=None, nick="", chan=""):

    """
    Begins a dialectic session.
    Syntax: !dialectic [topic]
    """

    global dsc
    global trn
    global queue
    global queued

    if nick=="rawkies" or nick=="gnostikoi": # handlers of Zeno

        if dsc: # can't start a dialectic if it's already going
            reply("A dialectic is already in session.")

        else: # if dialectic is not currently happening...
            dsc = True # DIALECTIC: ENGAGE
            trn = False
            conn.cmd('TOPIC', [chan, inp]) # add topic from command
            conn.cmd('MODE '+chan+' +m') # change channel mode to 'moderated'
            say("Welcome to the dialectic... Queue is now open. When queueing, be sure to send me a private message.")

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
        queue = []
        queued = []
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
    global queue
    global queued

    if dsc:

        if nick in queued: # if you've already been blacklisted...
            reply("The queue has not yet emptied. You have not been re-added to the queue.") # nothing happens and you have to wait until the queue is empty

        else:
            queue.append(nick) # add to queue
            queued.append(nick) # add to blacklist for when person is eventually removed from queue
            reply("You have been added to the queue.")

    else:
        reply("A dialectic is not in session.")


@hook.singlethread # keeps running in the same thread so as not to spawn a bunch of while loops running simultaneously
@hook.regex(".") # triggers on every line sent from the channel
def heartbeat(inp, conn=None, say=None, chan=""):

    """
    Controls the flow of a dialectic session.
    """

    global dsc
    global trn
    global queue
    global queued
    global speaker
    global turn_length
    global turn_mark

    while dsc: # only loop if a dialectic session is in progress

        if trn: # if someone has the floor...

            if (datetime.datetime.utcnow()-turn_mark).seconds>turn_length: # if someone's turn is over...

                try:
                    conn.cmd('MODE '+chan+' -v '+speaker) # take them off the floor
                    say(speaker+"'s turn has expired.")
                    speaker = queue.pop(0) # pull the next person from queue. if queue is empty, throws IndexError
                    say(speaker+" has the floor.") # mention what happened
                    conn.cmd('MODE '+chan+' +v '+speaker) # give the next person the floor
                    turn_mark = datetime.datetime.utcnow() # mark the beginning of their turn

                except IndexError: # if queue is empty, this exception triggers when we try to get the next speaker
                    queued = [] # empty the blacklist
                    trn = False # set state so loop starts checking when queue is populated again
                    say("The queue is now empty. You are free to enter the queue again.")

        else: # if no one has the floor...

            if len(queue)!=0: # if someone entered the queue in the last interval...
                trn = True # someone has the floor now
                speaker = queue.pop(0) # get the name of the first person in the queue
                conn.cmd('MODE '+chan+' +v '+speaker) # give them voice
                say(speaker+" now has the floor.")
                turn_mark = datetime.datetime.utcnow() # mark beginning of turn

        time.sleep(interval) # only loop every *interval* seconds


#Pseudocode:
#1. Start session, stating topic of discussion.
#2. Queue is open, people can enter. Once they have entered they cannot enter again until the queue has fully emptied.
#3. No one can speak except ops/admins and the speaker who currently has the floor.
#4. If there is someone in the queue, give them a turn lasting some determined period of time. When that is over, move on to the next person.
#5. If no one is left in the queue, allow everyone to enter the queue again and check until someone enters. Give them a turn to speak. Repeat 4 and 5.
#Don't allow commands if they don't make sense.
