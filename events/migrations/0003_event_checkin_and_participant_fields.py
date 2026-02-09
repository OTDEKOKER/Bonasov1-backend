from django.db import migrations, models
import uuid


def populate_checkin_tokens(apps, schema_editor):
    Event = apps.get_model('events', 'Event')
    for event in Event.objects.filter(checkin_token__isnull=True):
        event.checkin_token = uuid.uuid4()
        event.save(update_fields=['checkin_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0002_eventphase'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='checkin_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=False, null=True),
        ),
        migrations.AddField(
            model_name='participant',
            name='email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='participant',
            name='organization_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RunPython(populate_checkin_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='event',
            name='checkin_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]

