# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2013 reddit
# Inc. All Rights Reserved.
###############################################################################

# Known bug: if a given listing hasn't had a submission in the
# allotted time (e.g. the year listing in a subreddit that hasn't had
# a submission in the last year), we won't write out an empty
# list. I'll call it a feature.

import sys

from r2.models import Link, Comment
from r2.lib.db.sorts import epoch_seconds, score, controversy
from r2.lib.db import queries
from r2.lib import mr_tools
from r2.lib.utils import timeago, UrlParser
from r2.lib.jsontemplates import make_fullname # what a strange place
                                               # for this function

thingcls_by_name = {
    "link": Link,
    "comment": Comment,
}


def join_things():
    mr_tools.join_things(('url', 'sr_id', 'author_id'))


def time_listings(intervals):
    cutoff_by_interval = {interval: epoch_seconds(timeago("1 %s" % interval))
                          for interval in intervals}

    @mr_tools.dataspec_m_thing(
        ("url", str),
        ("sr_id", int),
        ("author_id", int),
    )
    def process(thing):
        if thing.deleted:
            return

        thing_cls = thingcls_by_name[thing.thing_type]
        fname = make_fullname(thing_cls, thing.thing_id)
        thing_score = score(thing.ups, thing.downs)
        thing_controversy = controversy(thing.ups, thing.downs)

        for interval, cutoff in cutoff_by_interval.iteritems():
            if thing.timestamp < cutoff:
                continue

            yield ("user/%s/top/%s/%d" % (thing.thing_type, interval, thing.author_id),
                   thing_score, thing.timestamp, fname)
            yield ("user/%s/controversial/%s/%d" % (thing.thing_type, interval, thing.author_id),
                   thing_controversy, thing.timestamp, fname)

            if thing.spam:
                continue

            if thing.thing_type == "link":
                yield ("sr/link/top/%s/%d" % (interval, thing.sr_id),
                       thing_score, thing.timestamp, fname)
                yield ("sr/link/controversial/%s/%d" % (interval, thing.sr_id),
                       thing_controversy, thing.timestamp, fname)

                if thing.url:
                    for domain in UrlParser(thing.url).domain_permutations():
                        yield ("domain/link/top/%s/%s" % (interval, domain),
                               thing_score, thing.timestamp, fname)
                        yield ("domain/link/controversial/%s/%s" % (interval, domain),
                               thing_controversy, thing.timestamp, fname)

    mr_tools.mr_map(process)


def store_keys(key, maxes):
    category, thing_cls, sort, time, id = key.split("/")

    query = None
    if category == "user":
        if thing_cls == "link":
            query = queries._get_submitted(int(id), sort, time)
        elif thing_cls == "comment":
            query = queries._get_comments(int(id), sort, time)
    elif category == "sr":
        if thing_cls == "link":
            query = queries._get_links(int(id), sort, time)
    elif category == "domain":
        if thing_cls == "link":
            query = queries.get_domain_links(id, sort, time)
    assert query

    item_tuples = [tuple([item[-1]] + [float(x) for x in item[:-1]])
                   for item in maxes]
    query._replace(item_tuples)


def write_permacache(fd = sys.stdin):
    mr_tools.mr_reduce_max_per_key(lambda x: map(float, x[:-1]), num=1000,
                                   post=store_keys,
                                   fd = fd)
