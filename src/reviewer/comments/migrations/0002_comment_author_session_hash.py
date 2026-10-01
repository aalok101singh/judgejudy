"""One column so an anonymous poster can be counted, and therefore limited.

**The rate limit is count-derived, not counter-derived.** Rather than a separate
table of counters with its own expiry semantics, this asks the question the
control actually needs answered -- *"how many comments has this identity
produced in the last hour?"* -- by counting the comments that exist. There is no
state to keep in step, no cleanup job, and no way for a counter and the rows it
describes to disagree.

The cost is a query per post, which on SQLite is an indexed count over a handful
of rows. That is the right trade for a self-hosted portal with one writer.

``author_session_hash`` is a **SHA-256 of the session key**, never the key itself.
A session key is a bearer credential, and a row that survives moderation review is
a row somebody will read; hashing means a leaked dump cannot be replayed as a
login. The hash is not stable across sessions, so clearing cookies resets the
limit -- which is stated plainly in ``views.py`` rather than pretended away, and
is why an *account* is the stronger key and what ``invite`` exists to obtain.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("comments", "0001_initial_schema"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="author_session_hash",
            # **`default=""`, not `null=True`.** Null *and* blank would be two
            # ways for this column to say "no anonymous key", and a rate-limit
            # filter on one would silently miss the other. This project has now
            # recorded the same defect class three times in different shapes --
            # F-13 (an empty collection is a valid value), F-61 (a structural zero
            # read as a measurement) and the two representations of "no rows" in
            # the roster import. One absent value is the whole fix.
            #
            # Indexed because the rate-limit query filters on it and nothing else
            # does.
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "SHA-256 of the posting session key, for rate-limiting anonymous "
                    "comments. Empty when the comment is attributed to an account. "
                    "Never the session key itself."
                ),
                max_length=64,
            ),
        ),
    ]