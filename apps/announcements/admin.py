from django.contrib import admin

from apps.announcements.models import Announcement, AnnouncementRecipient


class AnnouncementRecipientInline(admin.TabularInline):
    model = AnnouncementRecipient
    fields = ('user', 'is_read', 'read_at')
    readonly_fields = ('read_at',)
    autocomplete_fields = ('user',)
    extra = 0


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'created_by',
        'recipient_type',
        'program',
        'level',
        'is_published',
        'published_at',
        'created_at',
    )
    list_filter = ('recipient_type', 'is_published', 'program', 'level', 'created_at', 'published_at')
    search_fields = (
        'title',
        'body',
        'created_by__school_id',
        'created_by__first_name',
        'created_by__last_name',
        'program__name',
        'program__code',
    )
    autocomplete_fields = ('created_by', 'program', 'level', 'specific_users')
    readonly_fields = ('created_at',)
    list_select_related = ('created_by', 'program', 'level')
    inlines = (AnnouncementRecipientInline,)
    date_hierarchy = 'created_at'


@admin.register(AnnouncementRecipient)
class AnnouncementRecipientAdmin(admin.ModelAdmin):
    list_display = ('announcement', 'user', 'is_read', 'read_at')
    list_filter = ('is_read', 'read_at', 'announcement__recipient_type')
    search_fields = (
        'announcement__title',
        'user__school_id',
        'user__first_name',
        'user__last_name',
    )
    autocomplete_fields = ('announcement', 'user')
    list_select_related = ('announcement', 'user')
    date_hierarchy = 'read_at'
