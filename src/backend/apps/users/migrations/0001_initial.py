# Generated migration for users app

from django.db import migrations, models
import django.contrib.auth.models
import django.contrib.auth.validators


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
                ("username", models.CharField(blank=True, error_messages={"unique": "A user with that username already exists."}, help_text="Optional public @username; NOT used for t.me link or publishing", max_length=150, null=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name="username")),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="email address")),
                ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
                ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be active. Unselect this instead of deleting accounts.", verbose_name="active")),
                ("telegram_id", models.BigIntegerField(help_text="Telegram user ID; required for authentication", unique=True)),
                ("is_banned", models.BooleanField(default=False, help_text="Account is blocked from posting")),
                ("is_deleted", models.BooleanField(default=False, help_text="Soft delete flag")),
                ("ads_auto_publish", models.BooleanField(default=True, help_text="Publishing ban - when False, ads go to DRAFT instead of ON_MODERATION")),
                ("deleted_at", models.DateTimeField(blank=True, help_text="Soft delete timestamp", null=True)),
                ("consent_given_at", models.DateTimeField(blank=True, help_text="GDPR consent given timestamp (US-A8 / decision F)", null=True)),
                ("consent_revoked_at", models.DateTimeField(blank=True, help_text="GDPR consent revoked timestamp", null=True)),
                ("hard_delete_at", models.DateTimeField(blank=True, help_text="Scheduled hard-delete timestamp (telegram_id nulled 30 days after consent withdrawal)", null=True)),
                ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to.", related_name="users", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="users", to="auth.permission", verbose_name="user permissions")),
            ],
            options={
                "db_table": "users",
            },
        ),
        migrations.CreateModel(
            name="LoginToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(db_index=True, help_text="SHA-256 of raw 32-char URL-safe token; raw token NEVER stored", max_length=64, unique=True)),
                ("telegram_id", models.BigIntegerField(blank=True, help_text="Filled by BOT on /start login_<token>", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Token creation timestamp")),
                ("expires_at", models.DateTimeField(help_text="+5 min from creation")),
                ("consumed_at", models.DateTimeField(blank=True, help_text="Filled by WEB on login completion", null=True)),
            ],
            options={
                "db_table": "login_tokens",
            },
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["consent_revoked_at"], name="IX_users_erasure_sweep"),
        ),
    ]