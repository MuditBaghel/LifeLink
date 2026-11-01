"""Form helpers shared by every app."""

from django import forms


class BootstrapFormMixin:
    """Adds the right Bootstrap class to each widget so templates stay clean."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple,
                                   forms.RadioSelect)):
                css = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            elif isinstance(widget, forms.Textarea):
                css = "form-control"
                widget.attrs.setdefault("rows", 3)
            elif isinstance(widget, forms.FileInput):
                css = "form-control"
            else:
                css = "form-control"
            widget.attrs["class"] = f"{existing} {css}".strip()
            if field.required and not isinstance(
                widget, (forms.CheckboxInput, forms.RadioSelect)
            ):
                widget.attrs.setdefault("aria-required", "true")


class BootstrapModelForm(BootstrapFormMixin, forms.ModelForm):
    pass


class BootstrapForm(BootstrapFormMixin, forms.Form):
    pass


class ContactForm(BootstrapForm):
    name = forms.CharField(
        max_length=120, label="Your name",
        widget=forms.TextInput(attrs={"placeholder": "Full name", "autocomplete": "name"}),
    )
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autocomplete": "email"}),
    )
    phone = forms.CharField(
        max_length=20, required=False, label="Phone (optional)",
        widget=forms.TextInput(attrs={"placeholder": "+91 ", "autocomplete": "tel"}),
    )
    subject = forms.CharField(
        max_length=160, label="Subject",
        widget=forms.TextInput(attrs={"placeholder": "How can we help?"}),
    )
    message = forms.CharField(
        label="Message",
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": "Share the details we need to act on."}),
    )
