"""Module for data transformation tasks."""

from celery import shared_task
from .models import City, PointOfInterest, District
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

# Data transformation tasks will be added here