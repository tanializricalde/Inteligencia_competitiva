from django import forms


class StyledFormMixin:
    """Apply the shared Tabler classes to Django-generated widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if widget.is_hidden:
                continue
            if isinstance(widget, forms.CheckboxInput):
                css_class = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css_class = "form-select"
            else:
                css_class = "form-control"
            current_classes = str(widget.attrs.get("class", "")).split()
            if css_class not in current_classes:
                current_classes.append(css_class)
            widget.attrs["class"] = " ".join(current_classes)
