# for creating an admin using python console
from app import db
from models import Faculty

admin = Faculty(name='Admin', email='admin@dev.com', password='admin123', is_admin=True)

db.session.add(admin)
db.session.commit()

print('Admin added!')
