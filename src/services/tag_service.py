from ..models import db, Tag

class TagService:
    @staticmethod
    def create_tag(data):
        tag = Tag(
            nome=data['nome'],
            cor=data['cor'],
            tecnico_id=data['tecnico_id']
        )
        db.session.add(tag)
        db.session.commit()
        return tag

    @staticmethod
    def delete_tag(id):
        tag = Tag.query.get_or_404(id)
        db.session.delete(tag)
        db.session.commit()
        return True

    @staticmethod
    def get_by_tecnico(tecnico_id):
        return Tag.query.filter_by(tecnico_id=tecnico_id).all()

    @staticmethod
    def get_all_unique():
        """
        Returns a list of unique tag definitions (nome, cor) used in the system,
        useful for autocomplete or filtering suggestions.
        """
        # SQLAlchemy distinct query
        return db.session.query(Tag.nome, Tag.cor).distinct().all()
