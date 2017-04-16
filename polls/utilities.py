import re , datetime

from .models import UserClick
from stemming.porter2 import stem

from .models import LinkMap , UserClick
from py2neo import Graph , NodeSelector
from pymongo import MongoClient

def sanitize(string):
	urls = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', string)
	for url in urls :
		string = string.replace(url , '<a class="ui link">' + url + '</a>')
	string = re.sub('[\n]+' , '<br />' , string)
	return string

def get_urls(string):
	urls = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', string)
	return urls

def readable_date(string):
	d = datetime.datetime.strptime(string, '%Y-%m-%d').date() # %Y-%m-%%d
	return d.strftime('%b %d , %Y')

def get_videos(q , uname):
	vids = {}
	words = re.sub("[^\w]+" , " " , q).split()
	stemmed_words = [stem(word) for word in words]
	for word in stemmed_words:
		videos = UserClick.objects.filter(username = uname , word = word)		
		for v in videos:
			vids[v.video_id] = vids.get(v.video_id , 0) + v.count*len(word) # need to change this
	return vids

def sort_dict(d): # in descending order of value !
	res = []
	for key in d:
		res.append({'id' : key , 'score' : d[key]})
	res.sort(key = lambda x : x['score'] , reverse = True)
	return res ;

def get_recos(username) :
	types = ["COMMON_DESC"]
	clicked = UserClick.objects.filter(username = username)
	videos = {} 
	for click in clicked :
		if videos.get(click.video_id , -1) == -1:
			videos[click.video_id] = 0
		videos[click.video_id] = videos[click.video_id] + click.count
	graph = Graph(password = 'password')
	selector = NodeSelector(graph)
	recos = {}
	for video in videos:
		selected = list(selector.select("Video" , id = video))[0]
		for t in types :
			rels = graph.match(start_node = selected , rel_type = t)
			other_id = ''
			for rel in rels :
				enode = rel.end_node()
				other_id = enode['id']
				if t == "SAME_CHANNEL":
					recos[other_id] = recos.get(other_id , 0) + 1
				else:
					recos[other_id] = recos.get(other_id , 0) + rel['no_common_words']
			rels = graph.match(end_node = selected , rel_type = t)
			for rel in rels :
				snode = rel.start_node()
				other_id = snode['id']
				if t == "SAME_CHANNEL":
					recos[other_id] = recos.get(other_id , 0) + 1
				else:
					recos[other_id] = recos.get(other_id , 0) + rel['no_common_words']

	sorted_recos = sort_dict(recos)[0:30]
	mc = MongoClient()
	db = mc.videos
	ids_list = [x['id'] for x in sorted_recos]	
	results = []
	for id1 in ids_list:
		doc = db.videos.find({"videoInfo.id" : id1})[0]
		res = {}
		res['video_id'] = doc['videoInfo']['id']
		res['title'] = doc['videoInfo']['snippet']['title']
		res['description'] = doc['videoInfo']['snippet']['description']
		res['tags'] = ' , '.join(doc['videoInfo']['snippet']['tags'])
		a = res['description'].encode('utf-8').strip()
		a = ''.join([i if ord(i) < 128 else '' for i in a])
		res['description'] = sanitize(a)
		res['channel'] = doc['videoInfo']['snippet']['channelTitle']
		res['date'] = readable_date(doc['videoInfo']['snippet']['publishedAt'].split('T')[0])
		res['url'] = LinkMap.objects.filter(global_link = doc['videoInfo']['snippet']['thumbnails']['default']['url'])[0].local_link
		res['score'] = recos[res['video_id']]
		results.append(res)
	return results