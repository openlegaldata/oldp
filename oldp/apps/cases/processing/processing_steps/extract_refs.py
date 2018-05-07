import logging
import re

import nltk
from django.utils.text import slugify

from oldp.apps.backend.processing import ProcessingError, AmbiguousReferenceError
from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.laws.models import LawBook
from oldp.apps.references.models import CaseReferenceMarker, ReferenceMarker

logger = logging.getLogger(__name__)


class ExtractRefs(CaseProcessingStep):
    description = 'Extract references'
    law_book_codes = None

    def __init__(self, law_refs=True, case_refs=True):
        super(ExtractRefs, self).__init__()

        self.law_refs = law_refs
        self.case_refs = case_refs

    def process(self, case: Case) -> Case:
        """
        Read case.content, search for references, add ref marker (e.g. [ref=1]xy[/ref]) to text, add ref data to case:

        case.refs {
            1: {
                section: ??,
                line: 1,
                word: 2,
                id: ecli://...,
            }
            2: {
                line: 2,
                word: 123,
                id: law://de/bgb/123
            }
        }

        Ref data should contain position information, for CPA computations ...

        :param case_refs:
        :param law_refs:
        :param case:
        :return:
        """
        all_refs = []

        # print(case.get_sections())
        content = ReferenceMarker.remove_markers(case.content)

        if self.law_refs:
            content, refs = self.extract_law_refs(case, content, key=len(all_refs))
            all_refs.extend(refs)

            logger.debug('Extracted law refs: %i' % len(refs))

        if self.case_refs:
            content, refs = self.extract_case_refs(case, content, key=len(all_refs))
            all_refs.extend(refs)

            logger.debug('Extracted case refs: %i' % len(refs))

        case.content = content
        case.reference_markers = all_refs

        if not case._state.adding:
            case.save_reference_markers()
        else:
            logger.warning('Reference markers not saved (case is not saved)')

        # print(case.references)

        # if len(not_found_refs) > 0:
        #     raise ValueError('Some refs still in the content...')

        return case

    def test_ref_extraction(self, value):
        # (.+?)\\[/ref\\]
        value = re.sub(r'\[ref=([0-9]+)\](.+?)\[/ref\]', '______', value)

        if re.search(r'§', value, re.IGNORECASE):
            return value
        else:
            return None

    def get_law_book_codes(self):
        if self.law_book_codes is None:
            # Fetch codes from db
            # State.objects.values_list(
            self.law_book_codes = list(LawBook.objects.values_list('code', flat=True))
            logger.debug('Loaded law book codes from db: %i' % len(self.law_book_codes))

            # Extend with pre-defined codes
            self.law_book_codes.extend(['AsylG', 'VwGO', 'GkG', 'stbstg', 'lbo', 'ZPO', 'LVwG', 'AGVwGO SH', 'BauGB',
                                       'BauNVO', 'ZWStS', 'SbStG', 'StPO', 'TKG'])
        return self.law_book_codes

    # Returns regex for law book part in reference markers
    def get_law_book_ref_regex(self, optional=True, group_name=True, lower=False):
        # law_book_codes = list(json.loads(open(self.law_book_codes_path).read()).keys())
        law_book_codes = self.get_law_book_codes()
        law_book_regex = None
        for code in law_book_codes:
            if lower:
                code = code.lower()

            if law_book_regex is None:
                # if optional:
                #     law_book_regex = '('
                # else:
                #     law_book_regex = '('
                law_book_regex = ''

                # if group_name:
                #     law_book_regex += '?P<book>'

                law_book_regex += code
            else:
                law_book_regex += '|' + code
                # law_book_regex += ')'

                # if optional:
                # law_book_regex += '?'

        return law_book_regex

    def get_law_ref_regex(self):

        # TODO Regex builder tool? http://regexr.com/
        # https://www.debuggex.com/
        # ((,|und)\s*((?P<nos>[0-9]+)+)*
        # regex += '(\s?([0-9]+|[a-z]{1,2}|Abs\.|Abs|Satz|S\.|Nr|Nr\.|Alt|Alt\.|f\.|ff\.|und|bis|\,|'\
        #regex = r'(§|§§|Art.) (?P<sect>[0-9]+)\s?(?P<sect_az>[a-z]*)\s?(?:Abs.\s?(?:[0-9]{1,2})|Abs\s?(?:[0-9]{1,2}))?\s?(?:Satz\s[0-9]{1,2})?\s' + law_book_regex
        regex = r'(§|§§|Art\.)\s'
        regex += '(\s|[0-9]+|[a-z]|Abs\.|Abs|Satz|S\.|Nr|Nr\.|Alt|Alt\.|f\.|ff\.|und|bis|\,|' \
                 + self.get_law_book_ref_regex(optional=False, group_name=False) + ')+'
        regex += '\s(' + self.get_law_book_ref_regex(optional=False, group_name=False) + ')'

        regex_abs = '((Abs.|Abs)\s?([0-9]+)((,|und|bis)\s([0-9]+))*)*'

        regex_a = '(([0-9]+)\s?([a-z])?)'
        regex_a += '((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*'
        # f. ff.
        regex_a += '\s?((Abs.|Abs)\s?([0-9]+))*'
        # regex_a += '\s?(?:(Abs.|Abs)\s?(?:[0-9]{1,2})\s?((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*)?'
        # regex_a += '\s?((Satz|S\.)\s[0-9]{1,2})?'
        # regex_a += '\s?(((Nr|Nr\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'
        # regex_a += '\s?(((Alt|Alt\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'

        regex_a += '\s'
        regex_a += '(' + self.get_law_book_ref_regex(optional=True, group_name=False) + ')'

        # regex += regex_a
        # regex += '(\s?(,|und)\s' + regex_a + ')*'
        #
        # logger.debug('Law Regex=%s' % regex)

        return regex

    def get_law_ref_match_single(self, ref_str):
        # Single ref
        regex_a = '(Art\.|§)\s'
        regex_a += '((?P<sect>[0-9]+)\s?(?P<sect_az>[a-z])?)'                # f. ff.
        regex_a += '(\s?([0-9]+|[a-z]{1,2}|Abs\.|Abs|Satz|S\.|Nr|Nr\.|Alt|Alt\.|und|bis|,))*'
        # regex_a += '\s?(?:(Abs.|Abs)\s?(?:[0-9]{1,2})\s?((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*)?'
        # regex_a += '\s?((Satz|S\.)\s[0-9]{1,2})?'
        # regex_a += '\s?(((Nr|Nr\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'
        # regex_a += '\s?(((Alt|Alt\.)\s[0-9]+)' + '(\s?(,|und|bis)\s[0-9]+)*' + ')?'

        regex_a += '\s(?P<book>' + self.get_law_book_ref_regex(optional=False) + ')'

        return re.search(regex_a, ref_str)

    def get_law_ref_match_multi(self, ref_str):
        pattern = r'(?P<delimiter>§§|,|und|bis)\s?'
        pattern += '((?P<sect>[0-9]+)\s?'
        # pattern += '(?P<sect_az>[a-z])?)'
        # (?!.*?bis).*([a-z]).*)
        # pattern += '(?P<sect_az>(?!.*?bis).*([a-z]).*)?)'
        # (?!(moscow|outside))
        # pattern += '(?P<sect_az>(([a-z])(?!(und|bis))))?)'
        pattern += '((?P<sect_az>[a-z])(\s|,))?)'  # Use \s|, to avoid matching "bis" and "Abs", ...

        pattern += '(\s?(Abs\.|Abs)\s?([0-9]+))*'
        pattern += '(\s?(S\.|Satz)\s?([0-9]+))*'

        # pattern += '(?:\s(Nr\.|Nr)\s([0-9]+))'
        # pattern += '(?:\s(S\.|Satz)\s([0-9]+))'

        # pattern += '(?:\s(f\.|ff\.))?'
        pattern += '(\s?(f\.|ff\.))*'

        # pattern += '(\s(Abs.|Abs)\s?([0-9]+)((,|und|bis)\s([0-9]+))*)*'
        # pattern += '\s?(?:(Abs.|Abs)\s?(?:[0-9]{1,2})\s?((,|und|bis)\s*(([0-9]+)\s?([a-z])?)+)*)?'

        pattern += '\s?(?:(?P<book>' + self.get_law_book_ref_regex() + '))?'

        # print('MULTI: ' + ref_str)
        # print(pattern)

        # logger.debug('Multi ref regex: %s' % pattern)

        return re.finditer(pattern, ref_str)

    def get_law_id_from_match(self, match):
        # print(match.groups())

        return 'ecli://de/%s/%s%s' % (
            match.group('book').lower(),
            int(match.group('sect')),
            match.group('sect_az').lower()
        )

    def extract_law_refs(self, referenced_by: Case, content: str, key: int=0):
        """
        § 3d AsylG
        § 123 VwGO
        §§ 3, 3b AsylG
        § 77 Abs. 1 Satz 1, 1. Halbsatz AsylG
        § 3 Abs. 1 AsylG
        § 77 Abs. 2 AsylG
        § 113 Abs. 5 Satz 1 VwGO
        § 3 Abs. 1 Nr. 1 i.V.m. § 3b AsylG
        § 3a Abs. 1 und 2 AsylG
        §§ 154 Abs. 1 VwGO
        § 83 b AsylG
        § 167 VwGO iVm §§ 708 Nr. 11, 711 ZPO
        § 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO
        §§ 167 Abs. 2 VwGO, 708 Nr. 11, 711 ZPO
        §§ 52 Abs. 1; 53 Abs. 2 Nr. 1; 63 Abs. 2 GKG
        § 6 Abs. 5 Satz 1 LBO
        §§ 80 a Abs. 3, 80 Abs. 5 VwGO
        § 1 Satz 2 SbStG
        § 2 ZWStS
        § 6 Abs. 2 S. 2 ZWStS

        TODO all law-book jurabk

        :param referenced_by:
        :param key:
        :link https://www.easy-coding.de/Thread/5536-RegExp-f%C3%BCr-Gesetze/

        :param content:
        :return:
        """

        logger.debug('Extracting law references')

        refs = []
        results = list(re.finditer(self.get_law_ref_regex(), content))
        marker_offset = 0

        logger.debug('Current content value: %s' % content)
        logger.debug('Law refs found: %i' % len(results))

        for ref_m in results:

            ref_str = str(ref_m.group(0)).strip()
            law_ids = []

            # Handle single and multi refs separately
            if re.match(r'^(Art\.|§)\s', ref_str):
                law_ids = self.handle_single_law_ref(ref_str, law_ids)

            elif re.match(r'^§§\s', ref_str):
                law_ids = self.handle_multiple_law_refs(ref_str, law_ids)

            else:
                raise ProcessingError('Unsupported ref beginning: %s' % ref_str)

            ref = CaseReferenceMarker(referenced_by=referenced_by,
                                      text=ref_str,
                                      start=ref_m.start(),
                                      end=ref_m.end(),
                                      line=0)  # TODO
            ref.set_uuid()
            ref.set_references(law_ids)

            refs.append(ref)
            content, marker_offset = ref.replace_content(content, marker_offset, key + len(refs))

        return content, refs

    def handle_multiple_law_refs(self, ref_str, law_ids):
        # Search for multiple refs
        mms = self.get_law_ref_match_multi(ref_str)

        ids_tmp = []
        prev_sect = None
        prev_book = None

        logger.debug('Multi refs found in: %s' % ref_str)

        # Loop over all results
        for m in mms:

            # If book is not set, use __placeholder__ and replace later
            if m.group('book') is not None:
                book = m.group('book').lower()
            else:
                book = '__book__'

            # Section must exist
            if m.group('sect') is not None:
                sect = str(m.group('sect'))
            else:
                raise ProcessingError('Ref sect is not set')

            if m.group('sect_az') is not None:
                sect += m.group('sect_az').lower()

            law_id = {
                'book': book,
                'sect': sect,
                'type': 'law'
            }

            logger.debug('Law ID found: %s' % law_id)

            # Check for section ranges
            if m.group('delimiter') == 'bis':
                logger.debug('Handle section range - Add ids from ' + prev_sect + ' to ' + sect)
                # TODO how to handle az sects
                prev_sect = re.sub('[^0-9]', '', prev_sect)
                sect = re.sub('[^0-9]', '', sect)

                for between_sect in range(int(prev_sect)+1, int(sect)):
                    # print(between_sect)

                    ids_tmp.append({
                        'book': prev_book,
                        'sect': between_sect,
                        'type': 'law'
                    })
            else:
                prev_sect = sect
                prev_book = book

            ids_tmp.append(law_id)

        # law_ids.append('multi = ' + ref_str)
        # handle __book__
        logger.debug('All law ids found: %s' % ids_tmp)

        ids_tmp.reverse()
        book = None
        for id_tmp in ids_tmp:
            if id_tmp['book'] != '__book__':
                book = id_tmp['book']
            elif book is not None:
                id_tmp['book'] = book
            else:
                raise ProcessingError('Cannot determine law book (Should never happen): %s' % ref_str)

            law_ids.append(id_tmp)

        return law_ids

    def handle_single_law_ref(self, ref_str, law_ids):
        logger.debug('Single ref found in: %s' % ref_str)

        # Single ref
        mm = self.get_law_ref_match_single(ref_str)

        # Find book and section (only single result possible)
        if mm is not None:
            # mm.groupdict()

            if mm.group('book') is not None:
                # Found book
                book = mm.group('book').lower()
            else:
                raise ProcessingError('Ref book is not set: %s ' % ref_str)

            if mm.group('sect') is not None:
                # Found section
                sect = str(mm.group('sect'))
            else:
                raise ProcessingError('Ref sect is not set')

            if mm.group('sect_az') is not None:
                # Found section addon
                sect += mm.group('sect_az').lower()

            law_id = {
                'book': book,
                'sect': sect,
                'type': 'law'
            }

            logger.debug('Law ID: %s' % law_id)

            law_ids.append(law_id)
        else:
            law_ids.append({'book': 'not matched', 'sect': 'NOT MATCHED (single) %s ' % ref_str})
            logger.warning('Law ID could not be matched.')

        return law_ids

    def clean_text_for_tokenizer(self, text):
        """
        Remove elements from text that can make the tokenizer fail.

        :param text:
        :return:
        """
        def repl(m):
            return '_' * (len(m.group()))

        def repl2(m):
            # print(m.group(2))
            return m.group(1) + ('_' * (len(m.group(2)) + 1))

        # (...) and [...]
        text = re.sub(r'\((.*?)\)', repl, text)

        # Dates
        text = re.sub(r'(([0-9]+)\.([0-9]+)\.([0-9]+)|i\.S\.d\.)', repl, text)

        # Abbr.
        text = re.sub(r'(\s|\(|\[)([0-9]+|[IVX]+|[a-zA-Z]|sog|ca|Urt|Abs|Nr|lfd|vgl|Rn|Rspr|std|ff|bzw|Art)\.', repl2, text)

        # Schl.-Holst.
        text = re.sub(r'([a-z]+)\.-([a-z]+)\.', repl, text, flags=re.IGNORECASE)


        return text

    def get_court_name_regex(self):
        """
        Regular expression for finding court names

        :return: regex
        """
        # TODO Fetch from DB
        # TODO generate only once

        federal_courts = [
            'Bundesverfassungsgericht', 'BVerfG',
            'Bundesverwaltungsgericht', 'BVerwG',
            'Bundesgerichtshof', 'BGH',
            'Bundesarbeitsgericht', 'BAG',
            'Bundesfinanzhof', 'BFH',
            'Bundessozialgericht', 'BSG',
            'Bundespatentgericht', 'BPatG',
            'Truppendienstgericht Nord', 'TDG Nord',
            'Truppendienstgericht Süd', 'TDG Süd',
            'EUGH',
        ]
        states = [
            'Berlin',
            'Baden-Württemberg', 'BW',
            'Brandenburg', 'Brandenburgisches',
            'Bremen',
            'Hamburg',
            'Hessen',
            'Niedersachsen',
            'Hamburg',
            'Mecklenburg-Vorpommern',
            'Nordrhein-Westfalen', 'NRW',
            'Rheinland-Pfalz',
            'Saarland',
            'Sachsen',
            'Sachsen-Anhalt',
            'Schleswig-Holstein', 'Schl.-Holst.', 'SH',
            'Thüringen'
        ]
        state_courts = [
            'OVG',
            'VGH'
        ]
        cities = [
            'Baden-Baden',
            'Berlin-Brbg.'
            'Wedding',
            'Schleswig'
        ]
        city_courts = [
            'Amtsgericht', 'AG',
            'Landgericht', 'LG',
            'Oberlandesgericht', 'OLG',
            'OVG'
        ]

        pattern = None
        for court in federal_courts:
            if pattern is None:
                pattern = r'('
            else:
                pattern += '|'

            pattern += court

        for court in state_courts:
            for state in states:
                pattern += '|' + court + ' ' + state
                pattern += '|' + state + ' ' + court

        for c in city_courts:
            for s in cities:
                pattern += '|' + c + ' ' + s
                pattern += '|' + s + ' ' + c

        pattern += ')'

        # logger.debug('Court regex: %s' % pattern)

        return pattern

    def get_file_number_regex(self):
        return r'([0-9]+)\s([a-zA-Z]{,3})\s([0-9]+)/([0-9]+)'

    def extract_case_refs(self, referenced_by: Case, content: str, key: int=0):
        """
        BVerwG, Urteil vom 20. Februar 2013, - 10 C 23.12 -
        BVerwG, Urteil vom 27. April 2010 - 10 C 5.09 -
        BVerfG, Beschluss vom 10.07.1989, - 2 BvR 502, 1000, 961/86 -
        BVerwG, Urteil vom 20.02.2013, - 10 C 23.12 -
        OVG Nordrhein-Westfalen, Urteil vom 21.2.2017, - 14 A 2316/16.A -
        OVG Nordrhein-Westfalen, Urteil vom 29.10.2012 – 2 A 723/11 -
        OVG NRW, Urteil vom 14.08.2013 – 1 A 1481/10, Rn. 81 –
        OVG Saarland, Urteil vom 2.2.2017, - 2 A 515/16 -
        OVG Rheinland-Pfalz, Urteil vom 16.12.2016, -1A 10922/16 -
        Bayrischer VGH, Urteil vom 12.12.16, - 21 B 16.30364
        OVG Nordrhein-Westfalen, Urteil vom 21.2.2017, - 14 A 2316/16.A -
        Bayrischer VGH, Urteil vom 12.12.2016, - 21 B 16.30372 -
        OVG Saarland, Urteil vom 2.2.2017, - 2 A 515/16 -
        OVG Rheinland-Pfalz, Urteil vom 16.12.2016, -1A 10922/16 -
        VG Minden, Urteil vom 22.12.2016, - 1 K 5137/16.A -
        VG Gießen, Urteil vom 23.11.2016, - 2 K 969/16.GI.A
        VG Düsseldorf, Urteil vom 24.1.2017, - 17 K 9400/16.A
        VG Köln, Beschluss vom 25.03.2013 – 23 L 287/12 -
        OVG Schleswig, Beschluss vom 20.07.2006 – 1 MB 13/06 -
        Schleswig-Holsteinisches Verwaltungsgericht, Urteil vom 05.082014 – 11 A 7/14, Rn. 37 –
        Entscheidung des Bundesverwaltungsgerichts vom 24.01.2012 (2 C 24/10)

        EuGH Urteil vom 25.07.2002 – C-459/99 -

        TODO all court codes + case types

        - look for (Entscheidung|Bechluss|Urteil)
        - +/- 50 chars
        - find VG|OVG|Verwaltungsgericht|BVerwG|...
        - find location
        - find file number - ... - or (...)

        TODO

        Sentence tokenzier
        - remove all "special endings" \s([0-9]+|[a-zA-Z]|sog|Abs)\.
        - remove all dates

        :param key:
        :param content:
        :return:
        """

        refs = []
        original = content
        text = content

        # print('Before = %s'  % text)

        # Clean up text; replacing all chars that can lead to wrong sentences
        text = self.clean_text_for_tokenizer(text)

        # TODO
        from nltk.tokenize.punkt import PunktParameters
        punkt_param = PunktParameters()
        abbreviation = ['1', 'e', 'i']
        punkt_param.abbrev_types = set(abbreviation)
        # tokenizer = PunktSentenceTokenizer(punkt_param)

        offset = 0
        marker_offset = 0

        for start, end in nltk.PunktSentenceTokenizer().span_tokenize(text):
            length = end - start
            sentence = text[start:end]
            original_sentence = original[start:end]

            matches = list(re.finditer(r'\((.*?)\)', original_sentence))

            logger.debug('Sentence (matches: %i): %s' % (len(matches), sentence))
            logger.debug('Sentence (orignal): %s' % (original_sentence))

            for m in matches:
                # pass
                # print('offset = %i, len = %i' % (offset, len(sentence)))
                #
                # print('MANGLED: ' + sentence)
                logger.debug('Full sentence // UNMANGLED: ' + original_sentence)

                # focus_all = original[start+m.start(1):start+m.end(1)].split(',')
                focus_all = original_sentence[m.start(1):m.end(1)].split(',')


                # print(m.group(1))
                logger.debug('In parenthesis = %s' % focus_all)

                # Split
                for focus in focus_all:

                    # Search for file number
                    fns_matches = list(re.finditer(self.get_file_number_regex(), focus))

                    if len(fns_matches) == 1:
                        fn = fns_matches[0].group(0)
                        pos = fns_matches[0].start(0)

                        logger.debug('File number found: %s' % fn)

                        # Find court
                        court_name = None
                        court_pos = 999999
                        court_matches = list(re.finditer(self.get_court_name_regex(), original_sentence))

                        if len(court_matches) == 1:
                            # Yeah everything is fine
                            court_name = court_matches[0].group(0)

                        elif len(court_matches) > 0:
                            # Multiple results, choose the one that is closest to file number
                            for cm in court_matches:
                                if court_name is None or abs(pos - cm.start()) < court_pos:
                                    court_name = cm.group(0)
                                    court_pos = abs(pos - cm.start())
                        else:
                            # no court found, guess by search query
                            # probably the court of the current case? test for "die kammer"
                            pass

                        # Find date
                        # TODO

                        logger.debug('Filename = %s' % fn)
                        logger.debug('Courtname = %s' % court_name)

                        ref_start = start + m.start(1) + pos
                        ref_end = ref_start + len(fn)

                        if court_name is None:

                            # raise )
                            # TODO Probably same court as current case (use case validation)
                            logger.error(AmbiguousReferenceError('No court name found - FN: %s' % fn))
                            # logger.debug('Sentence: %s' % (fn, original_sentence)))
                            continue


                        ref_ids = [
                            {
                                'type': 'case',
                                'ecli': 'ecli://de/' + slugify(court_name) + '/' + slugify(fn.replace('/', '-'))
                            }
                        ]
                        # TODO maintain order for case+law refs
                        ref = CaseReferenceMarker(referenced_by=referenced_by,
                                                  text=focus,
                                                  start=ref_start,
                                                  end=ref_end,
                                                  line=0)  # TODO line number
                        ref.set_uuid()
                        ref.set_references(ref_ids)

                        refs.append(
                            ref
                        )

                        content, marker_offset = ref.replace_content(content, marker_offset, key + len(refs))

                        pass
                    elif len(fns_matches) > 1:
                        logger.warning('More file numbers found: %s' % fns_matches)

                        pass
                    else:
                        logger.debug('No file number found')

        return content, refs