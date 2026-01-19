from ..models import db, SavedView
from urllib.parse import parse_qs

class SavedViewService:
    @staticmethod
    def parse_query_string(query_string):
        """
        Parses a query string (e.g. '?status=Ativo') into a dictionary
        compatible with service filters.
        """
        if not query_string:
            return {}
            
        if query_string.startswith('?'):
            query_string = query_string[1:]
            
        parsed = parse_qs(query_string)
        flat_filters = {}
        for k, v in parsed.items():
            if len(v) == 1:
                flat_filters[k] = v[0]
            else:
                flat_filters[k] = v
        return flat_filters

    @staticmethod
    def save_view(user_id, page_route, name, query_string):
        """
        Saves a filtered view for a user.
        """
        view = SavedView(
            user_id=user_id,
            page_route=page_route,
            name=name,
            query_string=query_string
        )
        db.session.add(view)
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar
        return view

    @staticmethod
    def delete_view(id):
        view = SavedView.query.get_or_404(id)
        db.session.delete(view)
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar
        return True

    @staticmethod
    def get_for_user(user_id, page_route):
        """
        Get all saved views for a specific page and user.
        """
        return SavedView.query.filter_by(user_id=user_id, page_route=page_route).all()
