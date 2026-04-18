from apps.schedules.models import ClassTimetable


class TimetableService:

    @staticmethod
    def check_conflict(room, teacher, term, day_of_week, start_time, end_time, exclude_pk=None):
        """
        Returns 'room', 'teacher', or None.
        Time overlap: s1 < e2 AND s2 < e1.
        """
        base_qs = ClassTimetable.objects.filter(
            term=term,
            day_of_week=day_of_week,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if exclude_pk is not None:
            base_qs = base_qs.exclude(pk=exclude_pk)

        if base_qs.filter(room=room).exists():
            return 'room'
        if base_qs.filter(teacher=teacher).exists():
            return 'teacher'
        return None

    @staticmethod
    def create(validated_data):
        conflict = TimetableService.check_conflict(
            room=validated_data['room'],
            teacher=validated_data['teacher'],
            term=validated_data['term'],
            day_of_week=validated_data['day_of_week'],
            start_time=validated_data['start_time'],
            end_time=validated_data['end_time'],
        )
        if conflict:
            return None, conflict
        return ClassTimetable.objects.create(**validated_data), None

    @staticmethod
    def update(instance, validated_data):
        conflict = TimetableService.check_conflict(
            room=validated_data.get('room', instance.room),
            teacher=validated_data.get('teacher', instance.teacher),
            term=validated_data.get('term', instance.term),
            day_of_week=validated_data.get('day_of_week', instance.day_of_week),
            start_time=validated_data.get('start_time', instance.start_time),
            end_time=validated_data.get('end_time', instance.end_time),
            exclude_pk=instance.pk,
        )
        if conflict:
            return None, conflict
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance, None
