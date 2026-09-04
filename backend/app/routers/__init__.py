"""HTTP endpoints, one module per feature.

A *router* is FastAPI's word for a group of related endpoints. ``app/main.py``
attaches each one to the application, which keeps main.py short and makes any
feature easy to find:

    auth.py         register, login, /me, logout
    ml.py           image classification
    categories.py   date-fruit categories and their price statistics
    listings.py     create / edit / deactivate your own listings
    marketplace.py  the shared marketplace every logged-in user can read
    health.py       is the database up? is the model loaded?
"""
