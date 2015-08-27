from pprint import pprint
import xml.sax
from re import compile
from math import sqrt
import pymongo
import sys

RE_HOUSE_NUMBER = compile('(\d+)-(\d+)') # TODO: If possible, add ^ and/or $. Qualify with re.ASCII

ALLOWED_PLACES = ['city', 'town', 'village']
ALLOWED_HIGHWAYS = ['secondary', 'tertiary', 'unclassified', 'residential', 'service']


class NodeHandler(xml.sax.ContentHandler):
    def __init__(self, wanted_nodes):
        xml.sax.ContentHandler.__init__(self)
        self._nodes = {}
        self._wanted_nodes = wanted_nodes

    def startElement(self, name, attrs):
        if name == 'node':
            n_id = attrs['id']
            if n_id in self._wanted_nodes:
                n_lat = float(attrs['lat'])
                n_lng = float(attrs['lon'])
                n = (n_id, n_lat, n_lng)
                self._nodes[n_id] = n


class PlaceStreetHandler(xml.sax.ContentHandler):
    def __init__(self):
        xml.sax.ContentHandler.__init__(self)
        self._way = False
        self._streets = {}
        self._places = {}
        self._timbuks = {}
        self._node = False
        self._node_id = None
        self._place_collect = False
        self._seq = 0
        self._reset_addr()

    def _next_seq(self):
        seq = self._seq
        self._seq += 1
        return seq

    def _reset_addr(self):
        self._nodes = []
        self._addr_housenumber = ''
        self._addr_city = ''
        self._addr_street = ''
        self._highway = False

    def startElement(self, name, attrs):
        if name == 'way':
            self._way = True
            self._reset_addr()
        elif name == 'tag':
            if self._way or self._node:
                if attrs['k'] == 'addr:street':
                    self._addr_street = attrs['v']
                elif attrs['k'] == 'addr:housenumber':
                    self._addr_housenumber = attrs['v']
                elif attrs['k'] == 'addr:city':
                    self._addr_city = attrs['v']
                elif attrs['k'] == 'highway' and attrs['v'] in ALLOWED_HIGHWAYS:
                    self._highway = True
                elif attrs['k'] == 'name':
                    self._name = attrs['v']
            if self._node:
                if attrs['k'] == 'place' and attrs['v'] in ALLOWED_PLACES:
                    self._place_collect = True
                elif attrs['k'] == 'name':
                    self._name = attrs['v']
        elif name == 'nd':
            if self._way:
                self._nodes.append(attrs['ref'])
        elif name == 'node':
            self._node = True
            self._reset_addr()
            self._node_id = attrs['id']
            self._nodes.append(attrs['id'])
            self._place_collect = False

    def _try_save_addr(self):
        if not self._nodes:
            return

        if self._highway:
            self._captureTimbuk(self._name, '', self._nodes)

        if self._addr_street:
            if self._addr_city:
                self._captureStreet(self._addr_city, self._addr_street, '', self._nodes)
            else:
                self._captureTimbuk(self._addr_street, '', self._nodes)

        if self._addr_housenumber and self._addr_street:
            m = RE_HOUSE_NUMBER.match(self._addr_housenumber)
            if m:
                from_no, to_no = int(m.group(1)), int(m.group(2))
                for no in range(from_no, to_no + 1):
                    if self._addr_city:
                        self._captureStreet(self._addr_city, self._addr_street, str(no), self._nodes)
                    else:
                        self._captureTimbuk(self._addr_street, str(no), self._nodes)
            else:
                if self._addr_city:
                    self._captureStreet(self._addr_city, self._addr_street, self._addr_housenumber, self._nodes)
                else:
                    self._captureTimbuk(self._addr_street, self._addr_housenumber, self._nodes)

    def endElement(self, name):
        if name == 'way':
            self._way = False
            self._try_save_addr()
        elif name == 'node':
            self._node = False
            self._try_save_addr()
            if self._place_collect:
                self._capturePlace(self._name, [self._node_id, ])

    def _captureStreet(self, place, name, no, nodes):
        place = place.strip()
        name = name.strip()
        no = no.strip()
        street = (place, name, no)
        if street in self._streets:
            self._streets[street].update(set(nodes))
        else:
            self._streets[street] = set(nodes)

    def _captureTimbuk(self, name, no, nodes):
        name = name.strip()
        no = no.strip()
        seq = self._next_seq()
        timbuk = (name, no, seq)
        if timbuk in self._timbuks:
            self._timbuks[timbuk].update(set(nodes))
        else:
            self._timbuks[timbuk] = set(nodes)

    def _capturePlace(self, place, nodes):
        place = place.strip()
        if place in self._places:
            self._places[place].update(set(nodes))
        else:
            self._places[place] = set(nodes)


def resolve_positions(wanted_nodes, nodes):
    positions = []
    for wanted_node in wanted_nodes:
        n_id, n_lat, n_lng = nodes[wanted_node]
        positions.append((n_lat, n_lng))
    return positions

def distance(p, q):
    if p == q:
        return 0
    else:
        return sqrt((q[0] - p[0]) ** 2 + ((q[1] - p[1]) ** 2))


def pick_position(positions):
    lats = 0
    lngs = 0

    # find the weighted average point
    for lat, lng in positions:
        lats += lat
        lngs += lng

    center = (lats / len(positions), lngs / len(positions))
    # find the closest one
    best = positions[0]
    best_dist = distance(center, best)

    for position in positions[1:]:
        position_dist = distance(center, position)
        if position_dist < best_dist:
            best = position
            best_dist = position_dist

    return best


def pick_nearest_place(position, places, street=''):
    best_place = places[0]
    best_d = distance(position, places[0][1])

    if street.startswith('Kullagatan'):
        print('begin ' + str(position))

    for place in places[1:]:
        place_name, place_position = place
        d = distance(position, place_position)
        if d < best_d:
            best_place = place
            best_d = d
            if street.startswith('Kullagatan'):
                print('  best place is now ' + best_place[0])

    if street.startswith('Kullagatan'):
        print('end')
    return best_place


def find_places_streets(path):
    print('  Parsing streets and timbuks...')
    ps_handler = PlaceStreetHandler()
    parser = xml.sax.make_parser()
    parser.setContentHandler(ps_handler)
    parser.parse(open(path, "r", encoding='utf-8'))

    wanted_nodes = set()

    for place_nodes in ps_handler._places.values():
        wanted_nodes.update(place_nodes)

    for street_nodes in ps_handler._streets.values():
        wanted_nodes.update(street_nodes)

    for timbuk_nodes in ps_handler._timbuks.values():
        wanted_nodes.update(timbuk_nodes)

    print('  Parsing nodes...')
    n_handler = NodeHandler(wanted_nodes)
    parser = xml.sax.make_parser()
    parser.setContentHandler(n_handler)
    parser.parse(open(path, "r", encoding='utf-8'))

    print('  Preparing %d places' % len(ps_handler._places.items()))
    places = []
    for place, place_nodes in ps_handler._places.items():
        places.append((place, pick_position(resolve_positions(place_nodes, n_handler._nodes))))

    print('  Preparing %d streets' % len(ps_handler._streets.items()))
    streets = []
    for street, street_nodes in ps_handler._streets.items():
        place, street, no = street
        streets.append((place, street, no, pick_position(resolve_positions(street_nodes, n_handler._nodes))))

    print('  Preparing %d timbuks' % len(ps_handler._timbuks.items()))
    for timbuk, timbuk_nodes in ps_handler._timbuks.items():
        street, no, seq = timbuk
        position = pick_position(resolve_positions(timbuk_nodes, n_handler._nodes))
        place = pick_nearest_place(position, places, street)
        streets.append((place[0], street, no, position))

    return places, streets


def make_searchable(name):
    return name.lower()


def osmload(path):
    print('Finding places and streets...')
    places, streets = find_places_streets(path)
    print('Found %d places and %d streets' % (len(places), len(streets)))

    input('Press enter to save...')

    client = pymongo.MongoClient()
    db = client.streetsmart

    db.places.drop()
    db.streets.drop()

    print('Saving places...')
    for k, place in enumerate(places):
        p = {
            'searchable_name': make_searchable(u'%s' % place[0]),
            'place_name': place[0],
            'location': place[1],
        }
        db.places.insert(p)
        if k % 1000 == 0 and k > 0:
            print('  ...%6d' % k)
    print('Done')

    print('Creating places index...')
    db.places.create_index([('location', pymongo.GEO2D)])
    print('Done')

    print('Saving streets...')
    for k, street in enumerate(streets):
        if street[2]:
            s = {
                'searchable_name': make_searchable(u'%s %s %s' % (street[1], street[2], street[0])),
                'place_name': street[0],
                'street_name': street[1],
                'house_number': street[2],
                'location': street[3],
            }
        else:
            s = {
                'searchable_name': make_searchable(u'%s %s' % (street[1], street[0])),
                'place_name': street[0],
                'street_name': street[1],
                'house_number': street[2],
                'location': street[3],
            }
        #pprint(s['searchable_name'])
        db.streets.insert(s)
        if k % 1000 == 0 and k > 0:
            print('  ...%6d' % k)
    print('Done')

    print('Creating streets index...')
    db.streets.create_index([('location', pymongo.GEO2D)])
    print('Done')

    client.disconnect()


if __name__ == '__main__':
    osmload(sys.argv[1])