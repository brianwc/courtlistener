# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0001_initial'),
        ('judges', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='position',
            name='court',
            field=models.ForeignKey(related_name='+', to='search.Court'),
        ),
        migrations.AddField(
            model_name='position',
            name='judge',
            field=models.ForeignKey(related_name='positions', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='position',
            name='predecessor',
            field=models.ForeignKey(blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='politicalaffiliation',
            name='judge',
            field=models.ForeignKey(related_name='political_affiliations', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='politicalaffiliation',
            name='politician',
            field=models.ForeignKey(related_name='political_affiliations', blank=True, to='judges.Politician', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='is_alias_of',
            field=models.ForeignKey(blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='judge',
            name='race',
            field=models.ManyToManyField(to='judges.Race', blank=True),
        ),
        migrations.AddField(
            model_name='education',
            name='judge',
            field=models.ForeignKey(related_name='educations', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='education',
            name='school',
            field=models.ForeignKey(to='judges.School'),
        ),
        migrations.AddField(
            model_name='career',
            name='judge',
            field=models.ForeignKey(related_name='careers', blank=True, to='judges.Judge', null=True),
        ),
        migrations.AddField(
            model_name='abarating',
            name='judge',
            field=models.ForeignKey(related_name='aba_ratings', blank=True, to='judges.Judge', null=True),
        ),
    ]
