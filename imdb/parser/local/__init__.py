"""
parser.local package (imdb package).

This package provides the IMDbLocalAccessSystem class used to access
IMDb's data through a local installation.
the imdb.IMDb function will return an instance of this class when
called with the 'accessSystem' argument set to "local" or "files".

Copyright 2004, 2005 Davide Alberani <da@erlug.linux.it> 

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""

import os
from stat import ST_SIZE

from imdb import IMDbBase
from imdb._exceptions import IMDbDataAccessError, IMDbError
from imdb.utils import analyze_title, build_title, analyze_name, \
                        build_name, re_titleRef, re_nameRef, re_episodes
from imdb.Person import Person
from imdb.Movie import Movie

from personParser import getFilmography, getBio, getAkaNames
from movieParser import getLabel, getMovieCast, getAkaTitles, parseMinusList, \
                        getPlot, getRatingData, getMovieMisc, getTaglines, \
                        getQuotes, getMovieLinks, getBusiness, getLiterature, \
                        getLaserdisc

from ratober import search_name, search_title
from utils import getFullIndex, sortBy, KeyFScan


_ltype = type([])
_dtype = type({})
_stypes = (type(''), type(u''))


class IMDbLocalAccessSystem(IMDbBase):
    """The class used to access IMDb's data through a local installation."""

    accessSystem = 'local'

    def __init__(self, dbDirectory, *arguments, **keywords):
        """Initialize the access system.
        The directory with the files must be supplied.
        """
        IMDbBase.__init__(self, *arguments, **keywords)
        self.__db = os.path.expandvars(dbDirectory)
        self.__db = os.path.expanduser(self.__db)
        if hasattr(os.path, 'realpath'):
            self.__db = os.path.realpath(self.__db)
        self.__db = os.path.normpath(self.__db)
        self.__db = self.__db + getattr(os.path, 'sep', '/')
        self.__db = os.path.normcase(self.__db)
        if not os.path.isdir(self.__db):
            raise IMDbDataAccessError, '"%s" is not a directory' % self.__db
        self.__namesScan = KeyFScan('%snames.key' % self.__db)
        self.__titlesScan = KeyFScan('%stitles.key' % self.__db)

    def _get_lastID(self, indexF):
        fsize = os.stat(indexF)[ST_SIZE]
        return (fsize / 4) - 1

    def get_lastMovieID(self):
        """Return the last movieID"""
        return self._get_lastID('%stitles.index' % self.__db)
    
    def get_lastPersonID(self):
        """Return the last personID"""
        return self._get_lastID('%snames.index' % self.__db)

    def _normalize_movieID(self, movieID):
        """Normalize the given movieID."""
        try:
            return int(movieID)
        except (ValueError, OverflowError):
            raise IMDbError, 'movieID "%s" can\'t be converted to integer' % \
                            movieID

    def _normalize_personID(self, personID):
        """Normalize the given personID."""
        try:
            return int(personID)
        except (ValueError, OverflowError):
            raise IMDbError, 'personID "%s" can\'t be converted to integer' % \
                            personID

    def _get_real_movieID(self, movieID):
        """Handle title aliases."""
        rid = getFullIndex('%saka-titles.index' % self.__db, movieID,
                            kind='akatidx')
        if rid is not None: return rid
        return movieID

    def _get_real_personID(self, personID):
        """Handle name aliases."""
        rid = getFullIndex('%saka-names.index' % self.__db, personID,
                            kind='akanidx')
        if rid is not None: return rid
        return personID

    def _searchIMDbMoP(self, params):
        """Fetch the given web page from the IMDb akas server."""
        import urllib
        from imdb.parser.http import IMDbURLopener
        params = urllib.urlencode(params)
        url = 'http://akas.imdb.com/find?%s' % params
        content = ''
        try:
            urlOpener = IMDbURLopener()
            uopener = urlOpener.open(url)
            content = uopener.read()
            uopener.close()
            urlOpener.close()
        except (IOError, IMDbDataAccessError):
            pass
        return content

    def get_imdbMovieID(self, movieID):
        """Translate a movieID in an imdbID.
        Try an Exact Primary Title search on IMDb;
        return None if it's unable to get the imdbID.
        """
        titline = getLabel(movieID, '%stitles.index' % self.__db,
                            '%stitles.key' % self.__db)
        if not titline: return None
        params = {'q': titline, 's': 'pt'}
        content = self._searchIMDbMoP(params)
        if not content: return None
        from imdb.parser.http.searchMovieParser import BasicMovieParser
        mparser = BasicMovieParser()
        result = mparser.parse(content)
        if not (result and result.has_key('data')): return None
        return result['data'][0][0]

    def get_imdbPersonID(self, personID):
        """Translate a personID in an imdbID.
        Try an Exact Primary Name search on IMDb;
        return None if it's unable to get the imdbID.
        """
        name = getLabel(personID, '%snames.index' % self.__db,
                        '%snames.key' % self.__db)
        if not name: return None
        params = {'q': name, 's': 'pn'}
        content = self._searchIMDbMoP(params)
        if not content: return None
        from imdb.parser.http.searchPersonParser import BasicPersonParser
        pparser = BasicPersonParser()
        result = pparser.parse(content)
        if not (result and result.has_key('data')): return None
        return result['data'][0][0]

    def _findRefs(self, o, trefs, nrefs):
        """Find titles or names references in strings."""
        to = type(o)
        if to in _stypes:
            for title in re_titleRef.findall(o):
                rtitle = build_title(analyze_title(title, canonical=1),
                                    canonical=1)
                if trefs.has_key(rtitle): continue
                movieID = self.__titlesScan.getID(rtitle)
                if movieID is None:
                    movieID = self.__titlesScan.getID(title)
                if movieID is None: continue
                m = Movie(movieID=movieID, title=rtitle, accessSystem='local')
                trefs[rtitle] = m
            for name in re_nameRef.findall(o):
                rname = build_name(analyze_name(name, canonical=1),
                                    canonical=1)
                if nrefs.has_key(rname): continue
                personID = self.__namesScan.getID(rname)
                if personID is None:
                    personID = self.__namesScan.getID(name)
                if personID is None: continue
                p = Person(personID=personID, name=rname, accessSystem='local')
                nrefs[rname] = p
        elif to is _ltype:
            for item in o:
                self._findRefs(item, trefs, nrefs)
        elif to is _dtype:
            for value in o.values():
                self._findRefs(value, trefs, nrefs)
        return (trefs, nrefs)

    def _extractRefs(self, o):
        """Scan for titles or names references in strings."""
        trefs = {}
        nrefs = {}
        return self._findRefs(o, trefs, nrefs)

    def _search_movie(self, title, results):
        # ratober functions return a sorted
        # list of tuples (match_score, movieID, movieTitle)
        return [(x[1], analyze_title(x[2]))
                for x in search_title(title.strip(),
                '%stitles.key' % self.__db, results)]


    def get_movie_main(self, movieID):
        # Information sets provided by this method.
        infosets = ('main', 'vote details')
        tl = getLabel(movieID, '%stitles.index' % self.__db,
                        '%stitles.key' % self.__db)
        # No title, no party.
        if tl is None:
            raise IMDbDataAccessError, 'unable to get movieID "%s"' % movieID
        res = analyze_title(tl)
        # Build the cast list.
        actl = []
        for castG in ('actors', 'actresses'):
            midx = getFullIndex('%s%s.titles' % (self.__db, castG),
                            movieID, multi=1)
            if midx is not None:
                params = {'movieID': movieID,
                            'dataF': '%s%s.data' % (self.__db, castG),
                            'indexF': '%snames.index' % self.__db,
                            'keyF': '%snames.key' % self.__db,
                            'attrIF': '%sattributes.index' % self.__db,
                            'attrKF': '%sattributes.key' % self.__db,
                            'offsList': midx, 'doCast': 1}
                actl += getMovieCast(**params)
        if actl:
            actl[:] = sortBy(actl, 'position')
            res['cast'] = actl
        # List of other workers.
        works = ('producer', 'writer', 'cinematographer', 'composer',
                'costume-designer', 'director', 'editor', 'miscellaneou',
                'producer', 'production-designer', 'cinematographer')
        for i in works:
            index = getFullIndex('%s%ss.titles' % (self.__db, i),
                                    movieID, multi=1)
            if index is not None:
                params = {'movieID': movieID,
                            'dataF': '%s%s.data' % (self.__db, i),
                            'indexF': '%snames.index' % self.__db,
                            'keyF': '%snames.key' % self.__db,
                            'attrIF': '%sattributes.index' % self.__db,
                            'attrKF': '%sattributes.key' % self.__db,
                            'offsList': index}
                name = key = i
                if '-' in name:
                    name = name.replace('-', ' ')
                elif name == 'miscellaneou':
                    name = 'crewmembers'
                    key = 'miscellaneou'
                elif name == 'writer':
                    params['doWriters'] = 1
                params['dataF'] = '%s%ss.data' % (self.__db, key)
                data = getMovieCast(**params)
                if name == 'writer': data[:] = sortBy(data, 'order')
                res[name] = data
        # Rating.
        rt = self.get_movie_vote_details(movieID)['data']
        if rt: res.update(rt)
        # Various information.
        miscInfo = (('runtimes', 'running-times'), ('color info', 'color-info'),
                    ('genres', 'genres'), ('distributors', 'distributors'),
                    ('languages', 'language'), ('certificates', 'certificates'),
                    ('special effects companies', 'special-effects-companies'),
                    ('sound mix', 'sound-mix'), ('tech info', 'technical'),
                    ('production companies', 'production-companies'),
                    ('countries', 'countries'))
        for name, fname in miscInfo:
            params = {'movieID': movieID,
                'dataF': '%s%s.data' % (self.__db, fname),
                'indexF': '%s%s.index' % (self.__db, fname),
                'attrIF': '%sattributes.index' % self.__db,
                'attrKF': '%sattributes.key' % self.__db}
            data = getMovieMisc(**params)
            if data: res[name] = data
        if res.has_key('runtimes') and len(res['runtimes']) > 0:
            rt = res['runtimes'][0]
            episodes = re_episodes.findall(rt)
            if episodes:
                res['runtimes'][0] = re_episodes.sub('', rt)
                res['episodes'] = episodes[0]
        # AKA titles.
        akas = getAkaTitles(movieID,
                    '%saka-titles.data' % self.__db,
                    '%stitles.index' % self.__db,
                    '%stitles.key' % self.__db,
                    '%sattributes.index' % self.__db,
                    '%sattributes.key' % self.__db)
        if akas: res['akas'] = akas
        return {'data': res, 'info sets': infosets}

    def get_movie_plot(self, movieID):
        pl = getPlot(movieID, '%splot.index' % self.__db,
                                '%splot.data' % self.__db)
        trefs, nrefs = self._extractRefs(pl)
        if pl: return {'data': {'plot': pl},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}

    def get_movie_taglines(self, movieID):
        tg = getTaglines(movieID, '%staglines.index' % self.__db,
                        '%staglines.data' % self.__db)
        if tg: return {'data': {'taglines': tg}}
        return {'data': {}}

    def get_movie_keywords(self, movieID):
        params = {'movieID': movieID,
            'dataF': '%skeywords.data' % self.__db,
            'indexF': '%skeywords.index' % self.__db,
            'attrIF': '%sattributes.index' % self.__db,
            'attrKF': '%sattributes.key' % self.__db}
        kwds = getMovieMisc(**params)
        if kwds: return {'data': {'keywords': kwds}}
        return {'data': {}}

    def get_movie_alternate_versions(self, movieID):
        av = parseMinusList(movieID, '%salternate-versions.data' % self.__db,
                        '%salternate-versions.index' % self.__db)
        trefs, nrefs = self._extractRefs(av)
        if av: return {'data': {'alternate versions': av},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}

    def get_movie_crazy_credits(self, movieID):
        cc = parseMinusList(movieID, '%scrazy-credits.data' % self.__db,
                            '%scrazy-credits.index' % self.__db)
        trefs, nrefs = self._extractRefs(cc)
        if cc: return {'data': {'crazy credits': cc},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}

    def get_movie_goofs(self, movieID):
        goo = parseMinusList(movieID, '%sgoofs.data' % self.__db,
                            '%sgoofs.index' % self.__db)
        trefs, nrefs = self._extractRefs(goo)
        if goo: return {'data': {'goofs': goo},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}
    
    def get_movie_soundtrack(self, movieID):
        goo = parseMinusList(movieID, '%ssoundtracks.data' % self.__db,
                            '%ssoundtracks.index' % self.__db)
        trefs, nrefs = self._extractRefs(goo)
        if goo: return {'data': {'soundtrack': goo},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}

    def get_movie_quotes(self, movieID):
        mq = getQuotes(movieID, '%squotes.data' % self.__db,
                            '%squotes.index' % self.__db)
        trefs, nrefs = self._extractRefs(mq)
        if mq: return {'data': {'quotes': mq},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}

    def get_movie_release_dates(self, movieID):
        params = {'movieID': movieID,
            'dataF': '%srelease-dates.data' % self.__db,
            'indexF': '%srelease-dates.index' % self.__db,
            'attrIF': '%sattributes.index' % self.__db,
            'attrKF': '%sattributes.key' % self.__db}
        data = getMovieMisc(**params)
        if data: return {'data': {'release dates': data}}
        return {'data': {}}

    def get_movie_vote_details(self, movieID):
        data = getRatingData(movieID, '%sratings.data' % self.__db)
        return {'data': data}

    def get_movie_trivia(self, movieID):
        triv = parseMinusList(movieID, '%strivia.data' % self.__db,
                            '%strivia.index' % self.__db)
        trefs, nrefs = self._extractRefs(triv)
        if triv: return {'data': {'trivia': triv},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}

    def get_movie_locations(self, movieID):
        params = {'movieID': movieID,
            'dataF': '%slocations.data' % self.__db,
            'indexF': '%slocations.index' % self.__db,
            'attrIF': '%sattributes.index' % self.__db,
            'attrKF': '%sattributes.key' % self.__db}
        data = getMovieMisc(**params)
        if data: return {'data': {'locations': data}}
        return {'data': {}}

    def get_movie_connections(self, movieID):
        mc = getMovieLinks(movieID, '%smovie-links.data' % self.__db,
                            '%stitles.index' % self.__db,
                            '%stitles.key' % self.__db)
        if mc: return {'data': {'connections': mc}}
        return {'data': {}}

    def get_movie_business(self, movieID):
        mb = getBusiness(movieID, '%sbusiness.index' % self.__db,
                            '%sbusiness.data' % self.__db)
        trefs, nrefs = self._extractRefs(mb)
        if mb: return {'data': {'business': mb},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}
    
    def get_movie_literature(self, movieID):
        ml = getLiterature(movieID, '%sliterature.index' % self.__db,
                            '%sliterature.data' % self.__db)
        trefs, nrefs = self._extractRefs(ml)
        if ml: return {'data': {'literature': ml},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}
    
    def get_movie_laserdisc(self, movieID):
        ml = getLaserdisc(movieID, '%slaserdisc.index' % self.__db,
                            '%slaserdisc.data' % self.__db)
        trefs, nrefs = self._extractRefs(ml)
        if ml: return {'data': {'laserdisc': ml},
                        'titlesRefs': trefs, 'namesRefs': nrefs}
        return {'data': {}}

    def _search_person(self, name, results):
        # ratober functions return a sorted
        # list of tuples (match_score, personID, personName)
        return [(x[1], analyze_name(x[2]))
                for x in search_name(name.strip(),
                '%snames.key' % self.__db, results)]

    def get_person_main(self, personID):
        infosets = ('main', 'biography', 'other works')
        nl = getLabel(personID, '%snames.index' % self.__db,
                        '%snames.key' % self.__db)
        # No name, no party.
        if nl is None:
            raise IMDbDataAccessError, 'unable to get personID "%s"' % personID
        res = analyze_name(nl)
        res.update(getBio(personID, '%sbiographies.index' % self.__db,
                    '%sbiographies.data' % self.__db))
        akas = getAkaNames(personID,
                    '%saka-names.data' % self.__db,
                    '%snames.index' % self.__db,
                    '%snames.key' % self.__db)
        if akas: res['akas'] = akas
        trefs, nrefs = self._extractRefs(res)
        return {'data': res, 'info sets': infosets,
                'titlesRefs': trefs, 'namesRefs': nrefs}

    def get_person_filmography(self, personID):
        res = {}
        works = ('actor', 'actresse', 'producer', 'writer',
                'cinematographer', 'composer', 'costume-designer',
                'director', 'editor', 'miscellaneou', 'producer',
                'production-designer')
        for i in works:
            index = getFullIndex('%s%ss.names' % (self.__db, i), personID)
            if index is not None:
                params = {'offset': index,
                            'indexF': '%stitles.index' % self.__db,
                            'keyF': '%stitles.key' % self.__db,
                            'attrIF': '%sattributes.index' % self.__db,
                            'attrKF': '%sattributes.key' % self.__db}
                name = key = i
                if '-' in name:
                    name = name.replace('-', ' ')
                elif name == 'actresse':
                    name = 'actress'
                    params['doCast'] = 1
                elif name == 'miscellaneou':
                    name = 'miscellaneouscrew'
                    key = 'miscellaneou'
                elif name == 'actor':
                    params['doCast'] = 1
                elif name == 'writer':
                    params['doWriters'] = 1
                params['dataF'] = '%s%ss.data' % (self.__db, key)
                data = getFilmography(**params)
                data[:] = sortBy(data, 'year', remove=0, reverse=1)
                res[name] = data
        return {'data': res}

    def get_person_biography(self, personID):
        return self.get_person_main(personID)

    def get_person_other_works(self, personID):
        return self.get_person_main(personID)

