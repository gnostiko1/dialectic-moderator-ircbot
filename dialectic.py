from util import hook
import collections
import datetime
import operator
import time
import re

# Introduction:
# trolls are unwelcome
# play nice. first warning is a kick, second is kickban
# queue is automatically sorted by number of turns taken, from smallest to largest. if you haven't spoken as much as some other guys, you will be prioritized
# during a given turn, you are able to vote for the previous speaker
# one send per turn

class Participant:

	score = {"+":1, ".":0, "-":-1}
	categories = ("accurate, insightful, logical")

	def __init__(self, nick):
		self.nick = nick
		self.num_turns = 0
		self.queue = False
		self.time_queued = datetime.datetime.utcnow()
		self.awards = collections.Counter()

	def add_to_queue(self):
		self.queue = True
		self.time_queued = datetime.datetime.utcnow()

	def remove_from_queue(self):
		self.queue = False

	def award_points(self, **ptargs):
		a = score[ptargs["a"]]
		i = score[ptargs["i"]]
		l = score[ptargs["l"]]
		self.awards["a"] += a
		self.awards["i"] += i
		self.awards["l"] += l
		db.execute("update dialectic_log set accuracy=?, insight=?, logic=? where nick=? order by timestamp desc limit 1)", (a, i, l, self.nick)) # for the log
		db.execute("update points set accuracy=accuracy+?, insight=insight+?, logic=logic+? where nick=?", (a, i, l, self.nick)) # for persistent points system
		db.commit()

	def voice(self, conn, chan):
		conn.cmd('MODE ' + chan + ' +v '+self.nick)
		self.num_turns += 1

	def unvoice(self, conn, chan):
		conn.cmd('MODE ' + chan + ' -v '+self.nick)


#state variables for flow control
dsc = False
trn = False
vote_start = False
vote_agree = False
vote_end = False

#packaged for cleaner hooks
state = {"dialectic":dsc, "turn":trn, "vote":{"start":vote_start, "agree":vote_agree, "end":vote_end}}

#packaged for cleaner hooks
participants = [[], {}, []]

#results of votes
start_votes = collections.Counter()
agree_votes = collections.Counter()
end_votes = collections.Counter()

#packaged for cleaner hooks
votes = {"start":start_votes, "agree":agree_votes, "end":end_votes}

#store everything else in one dict for easy movement
other_vars = {}


@hook.regex(".")
def logger(match, db=None, paraml=None, bot=None, chan="", nick=""):
	global state
	global other_vars
	if state["dialectic"] and paraml[0]=="#dialectics":
		db.execute("insert into dialectic_log(nick, message, timestamp)"
			"values(?,?,?)", (nick, paraml[1], datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
		db.commit()
		if nick!=bot.config.get("nick"):
			other_vars["turn_end"] = True


def save_log_to_text(db, topic):
	with open("Dialectic{}.txt".format(datetime.datetime.utcnow().strftime("%Y%m%d%H%M")), "w") as f:
		f.write("Topic of the discussion: "+topic)
		f.write("Note: all timestamps in UTC")
		for line in db.execute("select * from dialectic_log order by timestamp").fetchall():
			f.write("{} | <{}> \"{}\" (a {:+d}; i {:+d}; l {:+d})".format(line[2], line[0], line[1], line[3], line[4], line[5]))


@hook.command
def dialectic(inp, db=None, conn=None, pm=None, reply=None, chan=""):
	'''Begins a dialectic. Usage: !dialectic [turn length in seconds] [topic]'''
	global state
	global votes
	global participants
	global other_vars

	if not state["dialectic"]:
		state["dialectic"] = True
		db.execute("create table if not exists dialectic_log(nick, message, timestamp, accuracy, insight, logic)")  # log for the session
		db.execute("create table if not exists points(nick, accuracy, insight, logic)")  # persistent tally
		db.execute("delete from dialectic_log")
		db.commit()
		parse = inp.split()

		try:
			other_vars["turn_length"] = int(parse[0])
			other_vars["topic"] = " ".join(parse[1:])
			conn.cmd('MODE ' + chan + " +m")

			state["vote"]["start"] = True
			votes["start"] = collections.Counter()
			conn.msg("#dialectics", "Should we apply the dialectic to the opinion '{}'? Vote 'yes' or 'no' in a private message to me. You may only participate in the dialectic if you answer this question.".format(other_vars["topic"]))
			time.sleep(60)
			state["vote"]["start"] = False

			if votes["start"]["yes"]/len(participants[0])>0.5:

				for n in participants[0]:
					pm("Before the dialectic begins, do you agree with the opinion, '{}'? Vote 'yes' or 'no' in a private message to me. To participate in the dialectic you must also answer this question.".format(other_vars["topic"]), nick=n)
				state["vote"]["agree"] = True
				other_vars["vote_mark"] = datetime.datetime.utcnow()
				while (datetime.datetime.utcnow()-other_vars["vote_mark"]).seconds<60 \
					and votes["agree"]["yes"]+votes["agree"]["no"]<len(participants[0]):
					time.sleep(1)
				state["vote"]["agree"] = False

				for n in participants[1]:
					pm("Welcome. This is how you queue...", nick=n)
				other_vars["turn_mark"] = datetime.datetime.utcnow()
				other_vars["turn_end"] = False

			else:
				conn.msg("#dialectics", "Unfortunately the vote did not meet the requirement.")
				conn.cmd('MODE' + chan + " -m")
		except ValueError:
			state["dialectic"] = False
			reply("Please fix the syntax: !dialectic [turn length in seconds] [opinion]")

	else:
		reply("Please wait until the current dialectic is finished.")


@hook.command
def cloture(inp, db=None, conn=None, pm=None):
	global state
	global votes
	global participants
	global other_vars

	if state["dialectic"]:
		state["dialectic"] = False
		state["turn"] = False

		for n in participants[1]:
			pm("A call for cloture has come. After this dialectic, do you think the opinion, '{}' is true or false?".format(other_vars["topic"]), nick=n)
		
		state["vote"]["end"] = True
		other_vars["vote_mark"] = datetime.datetime.utcnow()
		while (datetime.datetime.utcnow()-other_vars["vote_mark"]).seconds<60 \
			and votes["end"]["yes"]+votes["end"]["no"]<len(participants[1]):
			time.sleep(1)
		state["vote"]["end"] = False
		
		conn.msg("#dialectics", "Thank you all for participating. Before this dialectic it was the opinion of {}/{} of #dialectics that the opinion '{}' is true. After this dialectic it is the opinion of {}/{} of #dialectics that this opinion is true.".format(vote["agree"]["yes"], len(participants[1]), other_vars["topic"], vote["end"]["yes"], len(participants[2])))
		save_log_to_text(db, other_vars["topic"])


@hook.command
def queue(inp, reply=None, nick=""):
	global state
	global participants

	if state["dialectic"]:
		if not participants[1][nick].queue:
			participants[1][nick].add_to_queue()
		else:
			reply("You are already in the queue!")


@hook.command
def unqueue(inp, reply=None, nick=""):
	global state
	global participants

	if state["dialectic"]:
		if participants[1][nick].queue:
			participants[1][nick].remove_from_queue()
		else:
			reply("You are not in the queue!")


def get_queue(participants):
	return sorted(((p.nick) for p in participants[1] if p.queue), key=operator.attrgetter("num_turns", "time_queued"))


@hook.command
def whosup(inp, reply=None):
	global state
	global participants
	if state["dialectic"]:
		q = sorted(((p.nick) for p in participants[1] if p.queue), key=operator.attrgetter("num_turns", "time_queued"))
		if len(q)!=0:
			reply("Up next: " + ", ".join((("{}) {}".format(i+1, q[i].nick) for i in range(len(q))))))
		else:
			reply("The queue is empty. Feel free to enter by messaging me with '!queue'")


@hook.regex("^(yes|no)$", flags=re.IGNORECASE)
def voting(match, nick="", reply=None):
	global state
	global votes
	global participants

	if state["dialectic"]:

		if state["vote"]["start"] and nick not in participants[0]:
			participants[0].append(nick)
			votes["start"][match.group(1)] += 1
			reply("Thank you. Your vote has been recorded.")

		elif state["vote"]["agree"] and nick in participants[0] and nick not in participants[1].keys():
			participants[1][nick] = Participant(nick)
			votes["agree"][match.group(1)] += 1
			reply("Thank you. Your vote has been recorded.")

		elif state["vote"]["end"] and nick in participants[1].keys() and nick not in participants[2]:
			participants[2].append(nick)
			votes["end"][match.group(1)] += 1
			reply("Thank you. Your vote has been recorded.")


@hook.command
def award(inp):
	global other_vars
	pts = {}
	for c in ("a","i","l"):
		m = re.search("(?<={})(+|-)".format(c), "".join(inp.split())).group(1)
		if m!="":
			pts[c] = m
	participants[1][other_vars["last_speaker"]].award_points(pts)


@hook.command
def leaderboard(inp, db=None, reply=None):
	a = db.execute("select nick from points where accuracy=max(accuracy)").fetchall()
	apts = db.execute("select accuracy from points where nick=?", (a[0],)).fetchone()
	i = db.execute("select nick from points where insight=max(insight)").fetchall()
	ipts = db.execute("select insight from points where nick=?", (i[0],)).fetchone()
	l = db.execute("select nick from points where logic=max(logic)").fetchall()
	lpts = db.execute("select logic from points where nick=?", (l[0],)).fetchone()
	out = ""
	if len(a)==1:
		out += "The all-time leader in accuracy is {} with {} points. ".format(a[0], apts)
	else:
		out += "The all-time leaders in accuracy are " + ", ".join(a[:-1]) + "and {} with {} points. ".format(a[-1], apts)
	if len(i)==1:
		out += "The all-time leader in insight is {} with {} points. ".format(i[0], ipts)
	else:
		out += "The all-time leaders in insight are " + ", ".join(i[:-1]) + "and {} with {} points. ".format(i[-1], ipts)
	if len(l)==1:
		out += "The all-time leader in logic is {} with {} points. ".format(l[0], lpts)
	else:
		out += "The all-time leaders in logic are " + ", ".join(l[:-1]) + "and {} with {} points. ".format(l[-1], lpts)
	reply(out)


@hook.singlethread
@hook.regex(".")
def heartbeat(match, conn=None, chan=""):
	global state
	global participants
	global other_vars
	while state["dialectic"]:
		if state["turn"]:
			if (datetime.datetime.utcnow()-other_vars["turn_mark"]).seconds>other_vars["turn_length"] or other_vars["turn_end"]:
				other_vars["last_speaker"] = other_vars["speaker"]
				participants[1][other_vars["last_speaker"]].remove_from_queue()
				participants[1][other_vars["last_speaker"]].unvoice(conn, chan)
				other_vars["turn_end"] = False
				try:
					other_vars["speaker"] = get_queue(participants[1])[0]
					participants[1][other_vars["speaker"]].voice(conn, chan)
					other_vars["turn_mark"] = datetime.datetime.utcnow()
				except IndexError:
					conn.msg("#dialectics", "The queue is now empty. Feel free to enter with !queue")
					state["turn"] = False
		else:
			if len([p for p in participants[1].values() if p.queue])!=0:
				state["turn"] = True
				other_vars["speaker"] = get_queue(participants[1])[0]
				other_vars["turn_mark"] = datetime.datetime.utcnow()
				conn.msg(other_vars["speaker"], "You now have the floor.")
		time.sleep(1)
