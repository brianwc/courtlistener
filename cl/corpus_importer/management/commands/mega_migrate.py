"""A script to migrate the old data from one database to another, transforming
it as necessary along the way.
"""
from cl.corpus_importer.models_legacy import (
    Docket as DocketOld,
    Document as DocumentOld,
)
from cl.lib.db_tools import queryset_generator
from cl.alerts.models import (
    Alert as AlertNew,
)
from cl.audio.models import (
    Audio as AudioNew,
)
from cl.donate.models import (
    Donation as DonationNew,
)
from cl.favorites.models import (
    Favorite as FavoriteNew,
)
from cl.lib.model_helpers import disable_auto_now_fields
from cl.search.models import (
    Docket as DocketNew,
    Opinion as OpinionNew,
    OpinionsCited as OpinionsCitedNew,
    OpinionCluster as OpinionClusterNew,
    Court as CourtNew,
)
from cl.stats.models import Stat
from cl.users.models import (
    UserProfile as UserProfileNew
)

from collections import Counter
from datetime import datetime
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.utils.timezone import make_aware, utc, now
from juriscraper.lib.string_utils import CaseNameTweaker

# Disable auto_now and auto_now_add fields so that they can be copied over from
# the old database.
disable_auto_now_fields(AlertNew, AudioNew, FavoriteNew, DocketNew, CourtNew,
                        OpinionClusterNew, OpinionNew)


class Command(BaseCommand):
    help = 'Migrate all data for all apps from one DB to another.'
    case_name_tweaker = CaseNameTweaker()
    the_beginning_of_time = make_aware(datetime(1750, 1, 1), utc)

    def add_arguments(self, parser):
        parser.add_argument(
            '--search',
            action='store_true',
            default=False,
            help="Do migrations for the models in the search app: opinions, "
                 "oral args, and dockets"
        )
        parser.add_argument(
            '--citations',
            action='store_true',
            default=False,
            help="Do migrations for citations between objects"
        )
        parser.add_argument(
            '--user-stuff',
            action='store_true',
            default=False,
            help="Do migrations for user-related stuff (bar memberships, "
                 "alerts, favorites, donations, etc.)"
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            default=False,
            help="Do migrations for stats"
        )

    def handle(self, *args, **options):
        if options['search']:
            self.migrate_opinions_oral_args_and_dockets()
        if options['citations']:
            self.migrate_intra_object_citations()
        if options['user_stuff']:
            self.migrate_users_profiles_alerts_favorites_and_donations()
        if options['stats']:
            self.migrate_stats()

    @staticmethod
    def _none_to_blank(value):
        """Normalizes a field to be u'' instead of None. This is needed b/c the
        old models erroneously had null=True on a number of text fields. If they
        were set up properly according to Django conventions, they'd disallow
        null and have been set to blank instead.
        """
        if value is None:
            return u''
        else:
            return value

    def _get_case_names(self, case_name_orig):
        case_name_len = len(case_name_orig)
        max_case_name_len = 150
        if case_name_len > max_case_name_len:
            case_name = u''
            case_name_full = case_name_orig
        else:
            case_name = case_name_orig
            case_name_full = u''
        case_name_short = self.case_name_tweaker.make_case_name_short(
            case_name_orig)
        return case_name, case_name_full, case_name_short

    def _print_progress(self, progress, total, errors=None):
        """Print the progress of a migration subcomponent.

        If errors is provided it should be a dict of the form:

          errors = {
            'KeyError': 1982,
            'SomeOtherError': 42,
          }

        That is, error keys should be descriptive strings, and their values
        should be counts of how many times it happened.

        Note that using a collections.Counter object for this is very handy.
        """
        if not errors:
            errors = {}
        self.stdout.write("\r\tMigrated %s of %s (%d%%). Skipped %s: (%s)." % (
            progress,
            total,
            float(progress) / total * 100,
            sum(errors.values()),
            ', '.join(['%s: %s' % (k, v) for k, v in errors.items()]),
        ), ending='')
        self.stdout.flush()

    def migrate_opinions_oral_args_and_dockets(self):
        self.stdout.write("Migrating dockets, audio files, and opinions to new "
                          "database...")
        q = DocketOld.objects.using('old').all()
        old_dockets = queryset_generator(q)
        num_dockets = q.count()

        progress = 0
        self._print_progress(progress, num_dockets)
        for old_docket in old_dockets:
            # First do the docket, then create the cluster and opinion objects.
            try:
                old_audio = old_docket.audio_files.all()[0]
            except IndexError:
                old_audio = None
            try:
                old_document = old_docket.documents.all()[0]
            except IndexError:
                old_document = None
            if old_document is not None:
                old_citation = old_document.citation
                old_doc_case_name, old_doc_case_name_full, old_doc_case_name_short = self._get_case_names(old_citation.case_name)
            if old_audio is not None:
                old_audio_case_name, old_audio_case_name_full, old_audio_case_name_short = self._get_case_names(old_audio.case_name)

            court = CourtNew.objects.get(pk=old_docket.court_id)  # Courts are in place thanks to initial data.

            new_docket = DocketNew(
                pk=old_docket.pk,
                date_modified=old_docket.date_modified,
                date_created=old_docket.date_modified,
                court=court,
                case_name=old_doc_case_name,
                case_name_full=old_doc_case_name_full,
                case_name_short=old_doc_case_name_short,
                slug=self._none_to_blank(old_docket.slug),
                docket_number=self._none_to_blank(old_citation.docket_number),
                date_blocked=old_docket.date_blocked,
                blocked=old_docket.blocked,
            )
            if old_audio is not None:
                new_docket.date_argued = old_audio.date_argued
            new_docket.save(using='default')

            if old_document is not None:
                new_opinion_cluster = OpinionClusterNew(
                    pk=old_document.pk,
                    docket=new_docket,
                    judges=self._none_to_blank(old_document.judges),
                    date_modified=old_document.date_modified,
                    date_created=old_document.date_modified,
                    date_filed=old_document.date_filed,
                    slug=self._none_to_blank(old_citation.slug),
                    citation_id=old_document.citation_id,
                    case_name_short=old_doc_case_name_short,
                    case_name=old_doc_case_name,
                    case_name_full=old_doc_case_name_full,
                    federal_cite_one=self._none_to_blank(
                        old_citation.federal_cite_one),
                    federal_cite_two=self._none_to_blank(
                        old_citation.federal_cite_two),
                    federal_cite_three=self._none_to_blank(
                        old_citation.federal_cite_three),
                    state_cite_one=self._none_to_blank(
                        old_citation.state_cite_one),
                    state_cite_two=self._none_to_blank(
                        old_citation.state_cite_two),
                    state_cite_three=self._none_to_blank(
                        old_citation.state_cite_three),
                    state_cite_regional=self._none_to_blank(
                        old_citation.state_cite_regional),
                    specialty_cite_one=self._none_to_blank(
                        old_citation.specialty_cite_one),
                    scotus_early_cite=self._none_to_blank(
                        old_citation.scotus_early_cite),
                    lexis_cite=self._none_to_blank(old_citation.lexis_cite),
                    westlaw_cite=self._none_to_blank(old_citation.westlaw_cite),
                    neutral_cite=self._none_to_blank(old_citation.neutral_cite),
                    scdb_id=self._none_to_blank(
                        old_document.supreme_court_db_id),
                    source=old_document.source,
                    nature_of_suit=old_document.nature_of_suit,
                    citation_count=old_document.citation_count,
                    precedential_status=old_document.precedential_status,
                    date_blocked=old_document.date_blocked,
                    blocked=old_document.blocked,
                )
                new_opinion_cluster.save(
                    using='default',
                    index=False,
                )

                new_opinion = OpinionNew(
                    pk=old_document.pk,
                    cluster=new_opinion_cluster,
                    date_modified=old_document.date_modified,
                    date_created=old_document.time_retrieved,
                    type='010combined',
                    sha1=old_document.sha1,
                    download_url=old_document.download_url,
                    local_path=old_document.local_path,
                    plain_text=old_document.plain_text,
                    html=self._none_to_blank(old_document.html),
                    html_lawbox=self._none_to_blank(old_document.html_lawbox),
                    html_with_citations=old_document.html_with_citations,
                    extracted_by_ocr=old_document.extracted_by_ocr,
                )
                new_opinion.save(
                    using='default',
                    index=False,
                )

            if old_audio is not None:
                new_audio_file = AudioNew(
                    pk=old_audio.pk,
                    docket=new_docket,
                    source=old_audio.source,
                    case_name=old_audio_case_name,
                    case_name_short=old_audio_case_name_short,
                    case_name_full=old_audio_case_name_full,
                    judges=self._none_to_blank(old_audio.judges),
                    date_created=old_audio.time_retrieved,
                    date_modified=old_audio.date_modified,
                    sha1=old_audio.sha1,
                    download_url=old_audio.download_url,
                    local_path_mp3=old_audio.local_path_mp3,
                    local_path_original_file=old_audio.local_path_original_file,
                    duration=old_audio.duration,
                    processing_complete=old_audio.processing_complete,
                    date_blocked=old_audio.date_blocked,
                    blocked=old_audio.blocked,
                )
                new_audio_file.save(
                    using='default',
                    index=False,
                )

            progress += 1
            self._print_progress(progress, num_dockets)
        self.stdout.write(u'')  # Newline

    def migrate_intra_object_citations(self):
        """This method migrates the citations from one database to the other so
        that we don't have to run the citation finding algorithm immediately
        after the migration. Recall that in the legacy schema, Documents have a
        One-2-Many relationship with Citations. This algo handles two kinds of
        citations. The first is the simple case (1 to 1):

                        +--> C2--D2
                       /
            D1--cites--
                       \
                        +--> C3--D3

        This is handled by making a new connection such that D1 cites D2 and D3:

            D1 --cites--> D2

                  and

            D1 --cites--> D3

        The next kind of citation handled is more difficult. In this case,
        multiple Documents share a single Citation (1 to N).

                                 +--D2
                                 |
                        +--> C1--+
                       /         |
            D1--cites--          +--D3
                       \
                        +--> C2--D4

        This is handled by making the original document cite to all the targets:

            D1--cites-->D2
            D1--cites-->D3
            D1--cites-->D4

        """
        self.stdout.write("Migrating citation references to new database...")
        self.stdout.write("\tBuilding lookup dict of Citation IDs to "
                          "Document IDs...")
        # Build lookup dict in memory to avoid DB hits in a moment
        citation_document_pairs = DocumentOld.objects.using(
            'old'
        ).values_list(
            'citation_id',
            'pk'
        )
        # This dict takes the form of:
        #   {
        #      citation_id: [
        #        document_id1,
        #        document_id2,
        #        ...
        #      ],
        #      ...
        #   }
        #
        # The basic idea is that for any citation object's ID, you can lookup a
        # list of the documents that have it associated with them.
        cite_to_doc_dict = {}
        for citation_id, document_pk in citation_document_pairs:
            if citation_id in cite_to_doc_dict:
                cite_to_doc_dict[citation_id].append(document_pk)
            else:
                cite_to_doc_dict[citation_id] = [document_pk]

        # Iterate over all existing citations and move them to the correct place
        self.stdout.write(
            "\tBuilding list of all citations from Documents to Citations..."
        )
        DocumentCitationsOld = DocumentOld.cases_cited.through
        all_citations = DocumentCitationsOld.objects.using('old')
        total_count = all_citations.count()
        citation_values = all_citations.values_list(
            'document_id',
            'citation_id'
        )
        progress = 0
        errors = Counter()
        starting_point = 14514268  # For use with failed scripts.
        self._print_progress(progress, total_count, errors)
        new_citations = []
        for document_id, citation_id in citation_values:
            if progress < starting_point:
                errors.update(['AlreadyDone'])
                progress += 1
                continue
            # Early abort if the Citation object has been deleted from the DB.
            try:
                cited_documents = cite_to_doc_dict[citation_id]
            except KeyError:
                errors.update(['KeyError:OrphanCitation'])
                continue
            for cited_document in cited_documents:
                new_citations.append(
                    OpinionsCitedNew(
                        citing_opinion_id=document_id,
                        cited_opinion_id=cited_document,
                    )
                )
                if len(new_citations) % 100 == 0:
                    try:
                        OpinionsCitedNew.objects.using(
                            'default'
                        ).bulk_create(
                            new_citations
                        )
                    except IntegrityError:
                        # Loop through each opinion and save it, marking the
                        # failures. Could do this in the first place, but it's
                        # slower.
                        for new_citation in new_citations:
                            try:
                                new_citation.save()
                            except IntegrityError:
                                errors.update(['IntegrityError:CiteFromOrToMissingOpinionID'])
                                continue
                    new_citations = []

            progress += 1
            self._print_progress(progress, total_count, errors)

        # One final push if there's anything left.
        if len(new_citations) > 0:
            OpinionsCitedNew.objects.using('default').bulk_create(new_citations)
        self.stdout.write(u'')  # Newline

    def migrate_users_profiles_alerts_favorites_and_donations(self):
        self.stdout.write("Migrating users, profiles, alerts, favorites, and "
                          "donations to the new database...")
        old_users = User.objects.using('old').all()
        num_users = old_users.count()

        progress = 0
        self._print_progress(progress, num_users)
        for old_user in old_users:
            old_profile = old_user.profile_legacy
            old_alerts = old_profile.alert.all()
            old_favorites = old_profile.favorite.all()
            old_donations = old_profile.donation.all()

            new_user = User(
                pk=old_user.pk,
                username=old_user.username,
                first_name=old_user.first_name,
                last_name=old_user.last_name,
                email=old_user.email,
                is_staff=old_user.is_staff,
                is_active=old_user.is_active,
                is_superuser=old_user.is_superuser,
                date_joined=old_user.date_joined,
                last_login=old_user.last_login,
                password=old_user.password,
            )
            new_user.save(using='default')

            new_profile = UserProfileNew(
                pk=old_profile.pk,
                user=new_user,
                stub_account=old_profile.stub_account,
                employer=old_profile.employer,
                address1=old_profile.address1,
                address2=old_profile.address2,
                city=old_profile.city,
                state=old_profile.state,
                zip_code=old_profile.zip_code,
                avatar=old_profile.avatar,
                wants_newsletter=old_profile.wants_newsletter,
                plaintext_preferred=old_profile.plaintext_preferred,
                activation_key=old_profile.activation_key,
                key_expires=old_profile.key_expires,
                email_confirmed=old_profile.email_confirmed,
            )
            new_profile.save(using='default')
            new_profile.barmembership.add(
                *[membership.pk for membership in
                  old_profile.barmembership.all()]
            )

            for old_alert in old_alerts:
                new_alert = AlertNew(
                    pk=old_alert.pk,
                    user=new_user,
                    date_created=self.the_beginning_of_time,
                    date_modified=self.the_beginning_of_time,
                    name=old_alert.name,
                    query=old_alert.query,
                    rate=old_alert.rate,
                    always_send_email=old_alert.always_send_email,
                    date_last_hit=old_alert.date_last_hit,
                )
                new_alert.save(using='default')

            for old_favorite in old_favorites:
                opinion_fave_pk = getattr(old_favorite.doc_id, 'pk', None)
                audio_fave_pk = getattr(old_favorite.audio_id, 'pk', None)
                if opinion_fave_pk is not None:
                    cluster = OpinionClusterNew.objects.get(
                        pk=opinion_fave_pk)
                    audio = None
                else:
                    cluster = None
                    audio = AudioNew.objects.get(pk=audio_fave_pk)
                new_favorite = FavoriteNew(
                    pk=old_favorite.pk,
                    user=new_user,
                    cluster_id=cluster,
                    audio_id=audio,
                    date_created=old_favorite.date_modified or now(),
                    date_modified=old_favorite.date_modified or now(),
                    name=old_favorite.name,
                    notes=old_favorite.notes,
                )
                new_favorite.save(using='default')

            for old_donation in old_donations:
                new_donation = DonationNew(
                    pk=old_donation.pk,
                    donor=new_user,
                    date_modified=old_donation.date_modified,
                    date_created=old_donation.date_created,
                    clearing_date=old_donation.clearing_date,
                    send_annual_reminder=old_donation.send_annual_reminder,
                    amount=old_donation.amount,
                    payment_provider=old_donation.payment_provider,
                    payment_id=old_donation.payment_id,
                    transaction_id=old_donation.transaction_id,
                    status=old_donation.status,
                    referrer=old_donation.referrer,
                )
                new_donation.save(using='default')

            progress += 1
            self._print_progress(progress, num_users)
        self.stdout.write(u'')  # Do a newline...

    def migrate_stats(self):
        self.stdout.write("Migrating stats to the new database...")
        # Stats use the same model in new and old, with no db_table definitions.
        # Makes life oh-so-easy.
        old_stats = Stat.objects.using('old').all()
        stat_count = old_stats.count()

        progress = 0
        self._print_progress(progress, stat_count)
        for old_stat in old_stats:
            old_stat.save(using='default')
            progress += 1
            self._print_progress(progress, stat_count)
        self.stdout.write(u'')  # Do a newline...
