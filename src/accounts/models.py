import hashlib
from datetime import timedelta, datetime
from string import digits, ascii_uppercase
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
from django.db import models, IntegrityError
from django.utils import timezone
from django.utils.crypto import get_random_string

from core.helper import send_email


class UserManager(BaseUserManager):
    def create_user(self, email, password, username='', is_active=False):
        user = self.model(
            username=username,
            email=self.normalize_email(email=email).lower(),
            is_active=is_active
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, username=''):
        user = self.create_user(
            username=username,
            email=self.normalize_email(email=email).lower(),
            password=password,
        )
        user.is_admin = True
        user.is_active = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    email = models.EmailField(unique=True, verbose_name='Email')
    username = models.CharField(max_length=300, blank=True, verbose_name='Username')

    is_active = models.BooleanField(default=False, verbose_name='Active')
    is_admin = models.BooleanField(default=False, verbose_name='Admin')

    registered = models.DateTimeField(auto_now_add=True, verbose_name='Registered')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def send_email(self, subj, msg, html_msg=None):
        args, kwargs = (subj, msg, [self.email]), {'html_message': html_msg}
        send_email(*args, **kwargs)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def get_full_name(self):
        return self.email

    def get_short_name(self):
        return self.email

    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True

    def __str__(self):
        return self.email

    @property
    def is_staff(self):
        return self.is_admin

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'


def generate_random_code(length=6, allowed_chars=digits + ascii_uppercase):
    return get_random_string(length, allowed_chars)


def generate_security_token():
    return hashlib.sha1(str(datetime.now()).encode()).hexdigest()


def generate_expiration_date(duration=timedelta(minutes=10)):
    return timezone.now() + duration


class AuthCode(models.Model):
    ACTIVATION = 'activation'
    RECOVERY = 'recovery'
    LOGIN = 'login'

    PURPOSES = (
        (ACTIVATION, 'Activation'),
        (RECOVERY, 'Recovery'),
        (LOGIN, 'Login')
    )

    purpose = models.CharField(max_length=30, choices=PURPOSES, verbose_name='For')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_codes', verbose_name='User')
    code = models.CharField(default=generate_random_code, max_length=10, verbose_name='Code')
    security_token = models.CharField(default=generate_security_token, max_length=45, verbose_name='Security token')
    expires = models.DateTimeField(default=generate_expiration_date, verbose_name='Expiration date')

    def __str__(self):
        return '{} {} code'.format(self.user, self.purpose)

    def save(self, *args, **kwargs):
        AuthCode.objects.filter(expires__lte=timezone.now()).delete()
        try:
            if self.user.is_admin:
                self.code = '0' * len(generate_random_code())
            super().save(*args, **kwargs)
        except IntegrityError:
            AuthCode.objects.filter(purpose=self.purpose, user=self.user, code=self.code).delete()
            return self.save(*args, **kwargs)

    def email_user(self):
        if self.purpose == self.RECOVERY:
            subject = 'Password recovery'
            message = 'Some intro: {code}'.format(code=self.code)
        elif self.purpose == self.ACTIVATION:
            subject = 'Email activation'
            message = 'link'
        else:
            raise NotImplementedError
        self.user.send_email(subject, message)

    class Meta:
        unique_together = ('user', 'purpose', 'code')
        verbose_name = 'Auth code'
        verbose_name_plural = 'Auth codes'
