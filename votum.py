import requests
import json
import time
import math
import yaml
import websocket
from websocket import create_connection
from steem import Steem

if __name__ == '__main__':
    def vote_reserve(block, voter, postid, weight):
        while True:
            if block not in pending_votes:
                pending_votes[block] = {}
            if voter in pending_votes[block]:
                block += 1
            else:
                pending_votes[block][voter] = {postid:weight}
                break

    wsnode = "ws://127.0.0.1:8090"    # "wss://node.steem.ws"
    ws = create_connection(wsnode)
    with open("votum_config.yml", "r") as config_file:
        config = yaml.load(config_file)
        account_info = config["account_info"]
        voting_rule = config["voting_rule"]
        if voting_rule["mirror"] is None:
            rule_mirror = {}
        else:
            rule_mirror = voting_rule["mirror"]
        if voting_rule["follow"] is None:
            rule_follow = {}
        else:
            rule_follow = voting_rule["follow"]
        if voting_rule["tag"] is None:
            rule_tag = {}
        else:
            rule_tag = voting_rule["tag"]
        if voting_rule["reputation"] is None:
            rule_reputation = {}
        else:
            rule_reputation = voting_rule["reputation"]
    with open("votum_log.yml", "r") as log_file:
        log = yaml.load(log_file)
        last_block = log["last_block"]
        if log["pending"] is None:
            pending_votes = {}
        else:
            pending_votes = log["pending"]
        if log["complete"] is None:
            log["complete"] = {}
        else:
            complete_votes = log["complete"]
    if last_block == 0:
        send = ws.send(json.dumps({"jsonrpc": "2.0", "id": 0, "method": "call", "params": [0, "get_dynamic_global_properties", []]}))
        last_block = json.loads(ws.recv())["result"]["head_block_number"]
    while True:
        send = ws.send(json.dumps({"jsonrpc": "2.0", "id": 0, "method": "call", "params": [0, "get_block", [last_block]]}))
        res = json.loads(ws.recv())
        if res["result"] != None:
            if res["result"]["transactions"] != []:
                tx = res["result"]["transactions"]
                for i in tx:
                    for o in i["operations"]:
                        txtype = o[0]
                        if txtype == "comment" and o[1]["parent_author"] == "":
                            author = o[1]["author"]
                            postid = "@"+o[1]["author"]+"/"+o[1]["permlink"]
                            if author in rule_follow:
                                for v in rule_follow[author]:
                                    vote_block = last_block + int(rule_follow[author][v]["delay"]/3)
                                    weight = rule_follow[author][v]["weight"]
                                    vote_reserve(vote_block, v, postid, weight)
                            else:
                                if o[1]["json_metadata"] == "":
                                    tags = []
                                else:
                                    tags = json.loads(o[1]["json_metadata"])["tags"]
                                send = ws.send(json.dumps({"jsonrpc": "2.0", "id": 0, "method": "get_accounts", "params": [[author]]}))
                                rep_raw = float(json.loads(ws.recv())["result"][0]["reputation"])
                                if rep_raw == 0:
                                    rep = 50
                                elif rep_raw > 0:
                                    rep = int((math.log10(rep_raw)-9)*9+25)
                                else:
                                    rep = 50 - int((math.log10(-rep_raw)-9)*9+25)
                                if set(tags).intersection(rule_tag):
                                    valid_tags = set(tags).intersection(rule_tag)
                                    for t in valid_tags:
                                        for v in rule_tag[t]:
                                            if rep >= rule_tag[t][v]["reputation"]:
                                                vote_block = last_block + int(rule_tag[t][v]["delay"]/3)
                                                weight = rule_tag[t][v]["weight"]
                                                vote_reserve(vote_block, v, postid, weight)
                                elif rep >= min(rule_reputation):
                                    for r in sorted(rule_reputation):
                                        if rep >= r:
                                            for v in rule_reputation[r]:
                                                vote_block = last_block + int(rule_reputation[r][v]["delay"]/3)
                                                weight = rule_reputation[r][v]["weight"]
                                                vote_reserve(vote_block, v, postid, weight)
                                        else:
                                            break
                        if txtype == "vote":
                            voter = o[1]["voter"]
                            postid = "@"+o[1]["author"]+"/"+o[1]["permlink"]
                            if voter in rule_mirror:
                                for v in rule_mirror[voter]:
                                    weight = o[1]["weight"]/100 * rule_mirror[voter][v]["weight"]/100
                                    if rule_mirror[voter][v]["only_positive"] == True and weight < 0:
                                        pass
                                    else:
                                        vote_block = last_block + int(rule_mirror[voter][v]["delay"]/3)
                                        vote_reserve(vote_block, v, postid, weight)
            for i in sorted(pending_votes):
                if i <= last_block:
                    for v in pending_votes[i]:
                        for postid in pending_votes[i][v]:
                            weight = pending_votes[i][v][postid]
                            send = ws.send(json.dumps({"jsonrpc": "2.0", "id": 0, "method": "get_accounts", "params": [[v]]}))
                            current_voting_power = float(json.loads(ws.recv())["result"][0]["voting_power"])/100
                            if current_voting_power < account_info[v]["voting_power"]:
                                while True:
                                    j = i+1
                                    if j not in pending_votes:
                                        pending_votes[j] = {}
                                    if v not in pending_votes[j]:
                                        pending_votes[j][v] = {postid:weight}
                                        break
                            else:
                                if v not in complete_votes:
                                    complete_votes[v] = {}
                                if postid not in complete_votes[v]:
                                    try:
                                        Steem(wif=account_info[v]["posting_key"], node=wsnode).vote(postid, weight, v)
                                        print(postid, weight, v)
                                        complete_votes[v] = {postid:weight}
                                    except:
                                        pass
                    pending_votes.pop(i, None)
                else:
                    break
            print(str(last_block) + "  " + res["result"]["timestamp"] + "\r", end="")
            log["last_block"] = last_block
            log["pending"] = pending_votes
            log["complete"] = complete_votes
            with open("votum_log.yml", "w") as log_file:
                yaml.dump(log, log_file, default_flow_style=False)
            last_block += 1
        else:
            with open("votum_log.yml", "r") as log_file:
                log = yaml.load(log_file)
                pending_votes = log["pending"]
                complete_votes = log["complete"]
            time.sleep(time.time()%3)
