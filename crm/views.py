from django.shortcuts import render
from django.http import HttpResponse

def home(request):
    return HttpResponse("Hello! This is the homepage.")
