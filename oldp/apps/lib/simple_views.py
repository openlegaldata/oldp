from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.template.defaulttags import register
from django.urls import reverse
from django.views.generic import ListView


class SimpleButton(object):
    def __init__(self, name, url, css_class, icon):
        self.name = name
        self.url = url
        self.css_class = css_class
        self.icon = icon

    def get_url(self, obj=None):
        if obj is None:
            return reverse(self.url)
        else:
            return reverse(self.url, args=(obj.pk,))


@register.simple_tag
def get_button_url(button, obj):
    return button.get_url(obj)




class SimpleListView(ListView):
    paginate_by = 10
    list_display = ('name', )
    icon = 'fa fa-pencil'
    buttons = []
    item_buttons = []
    # ordering = ('name', )
    # def __init__(self, model, **kwargs):
    #     super().__init__(**kwargs)
    #     self.model = model

    def get_context_data(self, **kwargs):
        context = super(SimpleListView, self).get_context_data(**kwargs)

        print(self.model._meta)

        context.update({
            'title': self.model._meta.verbose_name_plural.title(),
            'icon': self.icon,
            'buttons': self.buttons,
            'item_buttons': self.item_buttons,
            'list_display': self.list_display,
            'model': self.model,
            'model_name': self.model._meta.verbose_name.title(),
            'model_name_plural': self.model._meta.verbose_name_plural.title(),
        })
        return context


class SimpleViews(object):
    use_generic_form_template = False

    def __init__(self, model, form, app_name):
        self.model = model
        self.form = form
        self.app_name = app_name
        self.model_name = self.model._meta.verbose_name.title()
        self.model_name_plural = self.model._meta.verbose_name_plural.title()

    def get_form_template(self):
        if self.use_generic_form_template:
            return 'form.html'
        else:
            return self.app_name + '/form.html'

    def set_auto_fields(self, obj, request):
        # Use this for user fields
        return obj

    def add(self, request):
        if request.method == 'POST':
            form = self.form(request.POST)

            if form.is_valid():
                obj = form.save(commit=False)

                obj = self.set_auto_fields(obj, request)
                obj.save()

                messages.success(request, '{} was successfully created.'.format(self.model_name))
                return redirect(reverse(self.app_name + ':index'))
        else:
            form = self.form()

        return render(request, self.get_form_template(), {
            'title': self.model_name,
            'form': form,
            'model_name': self.model_name,
        })

    def delete(self, request, item_id):
        obj = get_object_or_404(self.model, pk=item_id)
        obj.delete()

        messages.success(request, '{} was successfully deleted.'.format(self.model_name))
        return redirect(reverse(self.app_name + ':index'))

    def edit(self, request, item_id):
        obj = get_object_or_404(self.model, pk=item_id)

        if request.method == 'POST':
            form = self.form(request.POST, instance=obj)

            if form.is_valid():
                obj = form.save(commit=False)

                obj = self.set_auto_fields(obj, request)
                obj.save()

                messages.success(request, '{} was successfully updated.'.format(self.model_name))
                return redirect(reverse(self.app_name + ':edit', args=(obj.pk, )))

        else:
            form = self.form(instance=obj)

        return render(request, self.get_form_template(), {
            'title': obj.name,
            'obj': obj,
            'form': form,
            'model_name': self.model_name,
        })


class SimpleUserViews(SimpleViews):
    def set_auto_fields(self, obj, request):
        obj.user = request.user
        return obj
