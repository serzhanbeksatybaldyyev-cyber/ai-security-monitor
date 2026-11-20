from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import RegexValidator

from .models import UserProfile

USERNAME_RULE = RegexValidator(
    r"^[A-Za-z0-9_]{3,30}$",
    "Логин: от 3 до 30 символов, только латинские буквы, цифры и _.",
)


class StyledMixin:
    def style_fields(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class LoginForm(StyledMixin, AuthenticationForm):
    error_messages = {
        "invalid_login": "Неверный логин или пароль.",
        "inactive": "Учётная запись заблокирована администратором.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Логин"
        self.fields["password"].label = "Пароль"
        self.style_fields()

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            username = self.cleaned_data.get("username", "")
            password = self.cleaned_data.get("password", "")
            blocked = User.objects.filter(username__iexact=username, is_active=False).first()
            if blocked and blocked.check_password(password):
                raise forms.ValidationError("Учётная запись заблокирована администратором.", code="inactive")
            raise


class RegisterForm(StyledMixin, UserCreationForm):
    email = forms.EmailField(label="E-mail", error_messages={"invalid": "Введите e-mail в формате name@example.com."})

    class Meta:
        model = User
        fields = ("username", "email")
        labels = {"username": "Логин"}
        help_texts = {"username": "От 3 до 30 символов: латиница, цифры, _"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].validators = [USERNAME_RULE]
        self.fields["username"].error_messages["unique"] = "Этот логин уже занят."
        self.fields["password1"].label = "Пароль"
        self.fields["password1"].help_text = "Не менее 8 символов, не только цифры"
        self.fields["password2"].label = "Повторите пароль"
        self.fields["password2"].help_text = ""
        self.style_fields()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот e-mail уже зарегистрирован.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("store_sms_text", "preferred_language")
        labels = {"store_sms_text": "Хранить полный текст SMS в истории"}
        widgets = {
            "store_sms_text": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "preferred_language": forms.Select(attrs={"class": "form-select"}),
        }


class StyledPasswordChangeForm(StyledMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Текущий пароль"
        self.fields["new_password1"].label = "Новый пароль"
        self.fields["new_password1"].help_text = "Не менее 8 символов, не только цифры"
        self.fields["new_password2"].label = "Повторите новый пароль"
        self.error_messages = {
            **self.error_messages,
            "password_incorrect": "Текущий пароль введён неверно.",
            "password_mismatch": "Пароли не совпадают.",
        }
        self.style_fields()
