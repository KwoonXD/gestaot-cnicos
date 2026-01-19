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
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar
        return tag

    @staticmethod
    def delete_tag(id):
        tag = Tag.query.get_or_404(id)
        tecnico_id = tag.tecnico_id
        db.session.delete(tag)
        # db.session.commit() # REMOVIDO (P0.2): Caller deve commitar
        return tecnico_id

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
