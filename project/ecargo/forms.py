from django import forms
from .models import *
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class LoginForm(AuthenticationForm):
    username = forms.CharField(max_length=16, help_text='Maximum 16 Character',
                               widget=forms.TextInput(attrs={
                                   'placeholder': 'Username'
                               }))
    password = forms.CharField(label='Password',
                               widget=forms.PasswordInput(attrs={
                                   'placeholder': 'Password'
                               })
                               )