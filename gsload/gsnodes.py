#
# gsnodes.py - en del av Gatusmart, http://gatusmart.se
# Tillgängliggjord under Apache Software License 2.0, se LICENSE.txt
#

import xml.sax
import pymongo


INSERT_THRESHOLD = 100

class NodeHandler(xml.sax.ContentHandler):
    def __init__(self, db, wanted_nodes=set()):
        xml.sax.ContentHandler.__init__(self)
        self._all_nodes_wanted = len(wanted_nodes) == 0
        self._wanted_nodes = wanted_nodes
        self._db = db
        self._count = 0
        self._buffer = [ ]

    def startElement(self, name, attrs):
        if name == 'node':
            n_id = int(attrs['id'])
            if self._all_nodes_wanted or (n_id in self._wanted_nodes):
                n_lat = float(attrs['lat'])
                n_lng = float(attrs['lon'])
                self._buffer.append({
                    'id': n_id,
                    'location': [ n_lat, n_lng],
                })
                self._count += 1

                if self._count % INSERT_THRESHOLD == 0:
                    self._db.nodes.insert(self._buffer)
                    self._buffer = [ ]

    def flush(self):
        self._db.nodes.insert(self._buffer)


class NodeRepository(object):
    def __init__(self):
        self._client = pymongo.MongoClient()
        self._db = self._client.gsload

    def refresh(self, osm_file_path):
        self._db.nodes.drop()

        n_handler = NodeHandler(self._db)
        parser = xml.sax.make_parser()
        parser.setContentHandler(n_handler)
        parser.parse(open(osm_file_path, "r", encoding='utf-8'))

        self._db.nodes.create_index('id')
        return self._db.nodes.count()

    def find_by_id(self, n_id):
        cursor = self._db.nodes.find({ 'id': n_id })
        if cursor.count() > 0:
            node = cursor[0]
            return node
        else:
            return None