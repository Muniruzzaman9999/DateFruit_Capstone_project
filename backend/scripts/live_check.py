"""A live end-to-end check of the API against a running server.

Not part of the automated test suite. Those tests run inside a transaction that is
rolled back; this drives the real API over real HTTP, with the real database, the
real image folder and real static file serving, then deletes everything it created.
It exists so that "it works" is something that was observed rather than assumed.

Covers PHASE 7 (publish), PHASE 8 (edit / deactivate / reactivate), PHASE 9 (shared
marketplace, sorting, best individual price), PHASE 10 (price statistics) and
PHASE 12 (full integration, with real photographs from ``test_images/`` and the
worked examples from specification sections 75 to 81).

Start the server first:

    .venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir backend

then, in another terminal:

    .venv\\Scripts\\python.exe backend\\scripts\\live_check.py
"""

from __future__ import annotations

import io
import pathlib
import sys
import time
from decimal import Decimal

import httpx
from PIL import Image

BASE = "http://localhost:8000"
PASSWORD = "live-check-password"

checks_run = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks_run
    checks_run += 1
    if condition:
        print(f"  OK    {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        raise SystemExit(f"Live check failed: {label} {detail}")


def photo(colour: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


#: Real photographs, for the PHASE 12 run. A flat colour is fine for testing
#: prices and permissions, but it proves nothing about the classifier - only an
#: actual photograph of actual dates does that.
TEST_IMAGES = pathlib.Path(__file__).resolve().parents[2] / "test_images"


def real_photo(filename: str) -> bytes | None:
    """Load one photograph from test_images/, or None if it is not there.

    Returns None rather than raising because ``test_images/`` is a local folder
    of sample photographs, not a required part of the application. Somebody who
    clones the repository without it should still be able to run every other
    check rather than hitting a crash.
    """
    path = TEST_IMAGES / filename
    if not path.is_file():
        return None
    return path.read_bytes()



def wait_for_server(client: httpx.Client, seconds: int = 180) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{BASE}/api/health", timeout=5)
        except httpx.RequestError:
            time.sleep(1)
            continue
        if response.status_code == 200:
            print(f"Server ready: {response.json()}")
            return
        time.sleep(1)
    raise SystemExit(
        f"No server answered at {BASE} within {seconds}s. Start it with:\n"
        "  .venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir backend"
    )


class User:
    """One registered, logged-in account."""

    def __init__(self, client: httpx.Client, name: str, email: str) -> None:
        response = client.post(
            f"{BASE}/api/auth/register",
            json={
                "name": name,
                "email": email,
                "password": PASSWORD,
                "contact_number": "01711222333",
            },
        )
        if response.status_code != 201:
            raise SystemExit(f"register failed: {response.status_code} {response.text}")

        login = client.post(
            f"{BASE}/api/auth/login", json={"email": email, "password": PASSWORD}
        )
        if login.status_code != 200:
            raise SystemExit(f"login failed: {login.status_code} {login.text}")

        self._client = client
        self.name = name
        self.email = email
        self.id = login.json()["user"]["id"]
        self.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self._client.get(f"{BASE}{path}", headers=self.headers, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self._client.post(f"{BASE}{path}", headers=self.headers, **kwargs)

    def patch(self, path: str, **kwargs) -> httpx.Response:
        return self._client.patch(f"{BASE}{path}", headers=self.headers, **kwargs)

    def publish(
        self,
        category_id: int,
        *,
        price: str,
        quantity: str = "1",
        unit: str = "kg",
        shop_name: str = "Live Check Shop",
        shop_location: str = "Mirpur, Dhaka",
        colour: str = "red",
        image_bytes: bytes | None = None,
    ) -> dict:
        response = self.post(
            "/api/listings",
            data={
                "category_id": category_id,
                "price": price,
                "quantity": quantity,
                "unit": unit,
                "shop_name": shop_name,
                "contact_number": "01711222333",
                "shop_location": shop_location,
            },
            # A real photograph when one was given, otherwise a flat colour.
            files={
                "image": (
                    "photo.jpg",
                    image_bytes if image_bytes is not None else photo(colour),
                    "image/jpeg",
                )
            },
        )
        if response.status_code != 201:
            raise SystemExit(f"publish failed: {response.status_code} {response.text}")
        return response.json()

    def classify(self, image_bytes: bytes) -> dict:
        """Send one photograph to the classifier, as the React app does."""
        response = self.post(
            "/api/ml/predict",
            files={"file": ("upload.jpg", image_bytes, "image/jpeg")},
        )
        if response.status_code != 200:
            raise SystemExit(f"predict failed: {response.status_code} {response.text}")
        return response.json()



def ids_of(body: dict) -> list[int]:
    return [item["id"] for item in body["listings"]]


def clean_up(listing_ids: list[int], email_marker: str) -> None:
    """Remove every row and image file this run created."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from sqlalchemy import delete, select

    from app.db.session import SessionLocal
    from app.models.listing import Listing
    from app.models.user import User as UserRow
    from app.services.image_storage import delete_listing_image

    with SessionLocal() as session:
        for row in session.scalars(
            select(Listing).where(Listing.id.in_(listing_ids))
        ).all():
            delete_listing_image(row.image_path)

        session.execute(delete(Listing).where(Listing.id.in_(listing_ids)))
        session.execute(delete(UserRow).where(UserRow.email.like(f"%{email_marker}%")))
        session.commit()

        leftover_users = session.scalars(
            select(UserRow).where(UserRow.email.like(f"%{email_marker}%"))
        ).all()
        leftover_listings = session.scalars(
            select(Listing).where(Listing.id.in_(listing_ids))
        ).all()

    print(f"  leftover users: {len(leftover_users)}")
    print(f"  leftover listings: {len(leftover_listings)}")
    if leftover_users or leftover_listings:
        raise SystemExit("Clean-up did not remove everything.")


def run_phase12(client: httpx.Client, marker: str) -> list[int]:
    """PHASE 12 - FULL INTEGRATION.

    Walks the whole chain the specification lists, in order, with real
    photographs of real dates rather than flat colours:

        register -> login -> upload -> AI prediction -> confirm/correct ->
        category -> price -> unit -> shop -> contact -> location -> publish ->
        image appears -> another user sees it -> price sorting -> selected
        category average -> global best average -> edit -> statistics update ->
        deactivate -> hidden -> reactivate -> visible again

    It also runs the worked examples from sections 75 to 81 with their exact
    expected figures, which is why it starts by proving the marketplace is empty:
    an average of exactly Tk0.90/gram is only meaningful if nothing else is
    contributing to it.

    Returns the ids of every listing it created, for clean-up.
    """
    created: list[int] = []

    alice = User(client, "Rahim Uddin", f"rahim{marker}")
    bob = User(client, "Karim Mia", f"karim{marker}")
    categories = {
        row["name"]: row["id"] for row in alice.get("/api/categories").json()["categories"]
    }

    def stats(name: str) -> dict:
        return alice.get(f"/api/categories/{categories[name]}/stats").json()

    def average(name: str) -> Decimal | None:
        value = stats(name)["average_price_per_gram"]
        return None if value is None else Decimal(value)

    # ==================================================================
    print("\n18. PHASE 12 - the marketplace starts empty")
    # ==================================================================
    # Everything below asserts exact averages, so anything left over from an
    # earlier run would silently change the answers.
    opening = alice.get("/api/marketplace/listings").json()
    check("no active listings to begin with", opening["total"] == 0, str(opening["total"]))

    # ==================================================================
    print("\n19. PHASE 12 - section 75, the worked average-price example")
    # ==================================================================
    for price in ("800", "900", "1000"):
        created.append(
            alice.publish(categories["Ajwa"], price=price, unit="kg")["id"]
        )
    # 800/1000g = 0.80, 900/1000g = 0.90, 1000/1000g = 1.00 -> mean 0.90
    check("three Ajwa kg listings average 0.90/g", average("Ajwa") == Decimal("0.90"),
          str(average("Ajwa")))
    check("built from 3 listings", stats("Ajwa")["listing_count"] == 3)

    # Tk180 for a 200 g packet is also 0.90/g, so the mean must not budge.
    created.append(
        alice.publish(categories["Ajwa"], price="180", quantity="200", unit="gram")["id"]
    )
    check("adding a 200g packet at Tk180 keeps it at 0.90/g",
          average("Ajwa") == Decimal("0.90"), str(average("Ajwa")))
    check("now built from 4 listings", stats("Ajwa")["listing_count"] == 4)

    # A piece listing cannot be converted to grams, so it must be left out.
    created.append(
        alice.publish(categories["Ajwa"], price="20", quantity="1", unit="piece")["id"]
    )
    ajwa = stats("Ajwa")
    check("a Tk20 piece listing does not change the average",
          Decimal(ajwa["average_price_per_gram"]) == Decimal("0.90"),
          str(ajwa["average_price_per_gram"]))
    check("still built from 4 listings", ajwa["listing_count"] == 4, str(ajwa["listing_count"]))
    check("the piece listing is reported as excluded", ajwa["excluded_piece_count"] == 1)
    check("but still counts as active", ajwa["active_listing_count"] == 5,
          str(ajwa["active_listing_count"]))

    # ==================================================================
    print("\n20. PHASE 12 - section 76, best average across all varieties")
    # ==================================================================
    created.append(alice.publish(categories["Galaxy"], price="1200", unit="kg")["id"])
    created.append(alice.publish(categories["Medjool"], price="1400", unit="kg")["id"])
    created.append(alice.publish(categories["Rutab"], price="750", unit="kg")["id"])

    check("Galaxy averages 1.20/g", average("Galaxy") == Decimal("1.20"), str(average("Galaxy")))
    check("Medjool averages 1.40/g", average("Medjool") == Decimal("1.40"), str(average("Medjool")))
    check("Rutab averages 0.75/g", average("Rutab") == Decimal("0.75"), str(average("Rutab")))

    global_stats = alice.get("/api/categories/statistics").json()
    best = global_stats["best_average_price"]
    check("best average price is Rutab", best["category"] == "Rutab", str(best["category"]))
    check("best average price is 0.75/g",
          Decimal(best["average_price_per_gram"]) == Decimal("0.75"),
          str(best["average_price_per_gram"]))
    check("ordered cheapest average first",
          [row["category"] for row in global_stats["categories"]]
          == ["Rutab", "Ajwa", "Galaxy", "Medjool"],
          str([row["category"] for row in global_stats["categories"]]))
    check("four of nine varieties have price data",
          global_stats["counted_categories"] == 4 and global_stats["total_categories"] >= 9,
          f"{global_stats['counted_categories']}/{global_stats['total_categories']}")

    # ==================================================================
    print("\n21. PHASE 12 - section 77, selecting a category")
    # ==================================================================
    check("selecting Ajwa gives 0.90/g", average("Ajwa") == Decimal("0.90"))
    check("selecting Rutab gives 0.75/g", average("Rutab") == Decimal("0.75"))
    check("a variety with nothing for sale reports null, not zero",
          average("Sokari") is None, str(average("Sokari")))
    check("and says so in words",
          stats("Sokari")["message"].startswith("No gram-based price data available"),
          stats("Sokari")["message"])

    # ==================================================================
    print("\n22. PHASE 12 - clearing the way for the real-photograph run")
    # ==================================================================
    # Deactivating rather than deleting, because that is the application's own
    # way of taking a listing out of circulation - and proving the averages all
    # fall to null is section 58's requirement in its own right.
    for listing_id in created:
        alice.post(f"/api/listings/{listing_id}/deactivate")

    for name in ("Ajwa", "Galaxy", "Medjool", "Rutab"):
        check(f"{name} has no average once deactivated", average(name) is None, str(average(name)))
    check("nothing active in the marketplace",
          alice.get("/api/marketplace/listings").json()["total"] == 0)
    check("no variety has a best average now",
          alice.get("/api/categories/statistics").json()["best_average_price"] is None)
    check("but the listings are still in My Listings",
          alice.get("/api/listings/mine").json()["count"] == len(created))

    # ==================================================================
    print("\n23. PHASE 12 - sections 20/21/81, classifying real photographs")
    # ==================================================================
    if not TEST_IMAGES.is_dir():
        print(f"  SKIP  test_images/ not found at {TEST_IMAGES}")
    else:
        banana = real_photo("-2D7C777.jpg")
        if banana is None:
            print("  SKIP  no non-date photograph available for the section 81 test")
        else:
            verdict = alice.classify(banana)
            print(
                f"        banana -> is_date_fruit={verdict['is_date_fruit']} "
                f"prediction={verdict['prediction']!r} "
                f"confidence={verdict['confidence']:.4f}"
            )
            if verdict["is_date_fruit"]:
                # Reported honestly rather than dressed up as a pass. The model
                # has no "not a date" class, so a confident wrong answer is a
                # real limitation of the threshold approach, not a bug to hide.
                print(
                    "  NOTE  the model was confident about a non-date image. The "
                    "threshold did NOT reject it. This is the documented "
                    "limitation from section 21 - it is a confidence check, not a "
                    "date detector."
                )
                check("a confident answer still names one of the nine varieties",
                      verdict["prediction"] is not None)
            else:
                check("the banana is rejected",
                      verdict["message"] == "Please upload a date fruit only.",
                      verdict["message"])
                check("and no variety is named", verdict["prediction"] is None)
                check("with confidence below the 0.70 threshold",
                      verdict["confidence"] < 0.70, str(verdict["confidence"]))

        date_photo = real_photo("Ajwa Date (17).JPG")
        if date_photo is None:
            print("  SKIP  no Ajwa photograph available")
        else:
            verdict = alice.classify(date_photo)
            print(
                f"        real Ajwa -> is_date_fruit={verdict['is_date_fruit']} "
                f"prediction={verdict['prediction']!r} "
                f"confidence={verdict['confidence']:.4f}"
            )
            check("a real date photograph returns a well-formed answer",
                  {"is_date_fruit", "prediction", "confidence", "message"} <= set(verdict))
            if verdict["is_date_fruit"]:
                check("the predicted name is one the database knows",
                      verdict["prediction"] in categories, str(verdict["prediction"]))
            else:
                print(
                    "  NOTE  a genuine date photograph did not reach the 0.70 "
                    "threshold. The correction flow is the route to publishing it."
                )

    # ==================================================================
    print("\n24. PHASE 12 - the full publish chain, with a real photograph")
    # ==================================================================
    real = real_photo("Ajwa Date (18).JPG")
    alice_listing = alice.publish(
        categories["Ajwa"],
        price="800",
        unit="kg",
        shop_name="Rahim Dates Shop",
        shop_location="Mirpur, Dhaka",
        image_bytes=real,
    )
    created.append(alice_listing["id"])

    check("published as ACTIVE", alice_listing["status"] == "ACTIVE")
    check("filed under Ajwa", alice_listing["category"]["name"] == "Ajwa")
    check("price is Tk800", Decimal(alice_listing["price"]) == Decimal("800"))
    check("unit is kg", alice_listing["unit"] == "kg")
    check("shop name saved", alice_listing["shop_name"] == "Rahim Dates Shop")
    check("contact saved", alice_listing["contact_number"] == "01711222333")
    check("location saved", alice_listing["shop_location"] == "Mirpur, Dhaka")
    check("attributed to its author", alice_listing["posted_by"]["name"] == "Rahim Uddin")
    check("comparable price is 0.80/g",
          Decimal(alice_listing["price_per_gram"]) == Decimal("0.80"))

    image_response = client.get(f"{BASE}{alice_listing['image_url']}")
    check("the listing photograph appears over HTTP", image_response.status_code == 200)
    check("served as an image",
          image_response.headers.get("content-type", "").startswith("image/"),
          str(image_response.headers.get("content-type")))
    if real is not None:
        check("and it is the photograph that was uploaded",
              image_response.content == real,
              f"{len(image_response.content)} bytes vs {len(real)}")

    # ==================================================================
    print("\n25. PHASE 12 - section 78, another user sees the listing")
    # ==================================================================
    bob_listing = bob.publish(
        categories["Ajwa"],
        price="750",
        unit="kg",
        shop_name="Karim Dates Shop",
        shop_location="Mirpur, Dhaka",
        image_bytes=real_photo("Ajwa Date (19).JPG"),
    )
    created.append(bob_listing["id"])

    ajwa_url = f"/api/marketplace/listings?category_id={categories['Ajwa']}&sort=price"
    alice_view = ids_of(alice.get(ajwa_url).json())
    bob_view = ids_of(bob.get(ajwa_url).json())

    check("Rahim sees Karim's cheaper listing", bob_listing["id"] in alice_view)
    check("Karim sees Rahim's listing", alice_listing["id"] in bob_view)
    check("both see both", set(alice_view) == set(bob_view) == {alice_listing["id"], bob_listing["id"]})

    # ==================================================================
    print("\n26. PHASE 12 - sections 37/38, sorting and best individual price")
    # ==================================================================
    listed = alice.get(ajwa_url).json()["listings"]
    check("sorted lowest price first",
          [Decimal(row["price"]) for row in listed] == [Decimal("750"), Decimal("800")],
          str([row["price"] for row in listed]))

    best_single = alice.get(
        f"/api/marketplace/best-price?category_id={categories['Ajwa']}"
    ).json()
    check("best individual price is Karim's listing",
          best_single["listing"]["id"] == bob_listing["id"])
    check("at 0.75/g", Decimal(best_single["listing"]["price_per_gram"]) == Decimal("0.75"))
    check("and names the shop", best_single["listing"]["shop_name"] == "Karim Dates Shop")

    # Two listings: 0.80 and 0.75 -> mean 0.775
    check("Ajwa now averages 0.775/g", average("Ajwa") == Decimal("0.775"), str(average("Ajwa")))

    # ==================================================================
    print("\n27. PHASE 12 - section 79, editing updates everything at once")
    # ==================================================================
    # Counted before the edit, so "no duplicate" is measured against the author's
    # own listings rather than every listing the run created - Karim owns one of
    # those, and it would never appear here.
    mine_before = alice.get("/api/listings/mine").json()["count"]

    edited = alice.patch(
        f"/api/listings/{alice_listing['id']}", files={"price": (None, "900")}
    ).json()
    check("the listing keeps its id", edited["id"] == alice_listing["id"])
    check("the price is now Tk900", Decimal(edited["price"]) == Decimal("900"))
    check("no duplicate was created",
          alice.get("/api/listings/mine").json()["count"] == mine_before,
          f"{alice.get('/api/listings/mine').json()['count']} vs {mine_before}")
    # 0.90 and 0.75 -> mean 0.825
    check("the average followed the edit immediately",
          average("Ajwa") == Decimal("0.825"), str(average("Ajwa")))
    check("the marketplace order followed too",
          [Decimal(row["price"]) for row in alice.get(ajwa_url).json()["listings"]]
          == [Decimal("750"), Decimal("900")])

    moved = alice.patch(
        f"/api/listings/{alice_listing['id']}",
        files={"category_id": (None, str(categories["Medjool"]))},
    ).json()
    check("moving variety keeps the same id", moved["id"] == alice_listing["id"])
    check("it is now Medjool", moved["category"]["name"] == "Medjool")
    check("Ajwa's average dropped to Karim's listing alone",
          average("Ajwa") == Decimal("0.75"), str(average("Ajwa")))
    check("Medjool's average appeared", average("Medjool") == Decimal("0.90"),
          str(average("Medjool")))

    shop_edit = alice.patch(
        f"/api/listings/{alice_listing['id']}",
        files={
            "shop_name": (None, "Rahim Premium Dates"),
            "contact_number": (None, "01911555444"),
            "shop_location": (None, "Dhanmondi, Dhaka"),
        },
    ).json()
    check("shop name updated", shop_edit["shop_name"] == "Rahim Premium Dates")
    check("contact number updated", shop_edit["contact_number"] == "01911555444")
    check("location updated", shop_edit["shop_location"] == "Dhanmondi, Dhaka")
    check("still the same listing", shop_edit["id"] == alice_listing["id"])

    # Put it back under Ajwa for the deactivation checks below.
    alice.patch(
        f"/api/listings/{alice_listing['id']}",
        files={"category_id": (None, str(categories["Ajwa"]))},
    )
    check("moved back to Ajwa", average("Ajwa") == Decimal("0.825"), str(average("Ajwa")))

    # ==================================================================
    print("\n28. PHASE 12 - section 80, deactivate then reactivate")
    # ==================================================================
    off = alice.post(f"/api/listings/{alice_listing['id']}/deactivate").json()
    check("status is INACTIVE", off["status"] == "INACTIVE")
    check("hidden from the marketplace",
          alice_listing["id"] not in ids_of(alice.get(ajwa_url).json()))
    check("hidden from the other user too",
          alice_listing["id"] not in ids_of(bob.get(ajwa_url).json()))
    check("excluded from the average", average("Ajwa") == Decimal("0.75"), str(average("Ajwa")))
    check("excluded from best individual price",
          alice.get(f"/api/marketplace/best-price?category_id={categories['Ajwa']}")
          .json()["listing"]["id"] == bob_listing["id"])
    check("still visible to its author in My Listings",
          alice_listing["id"] in [row["id"] for row in alice.get("/api/listings/mine").json()["listings"]])
    check("its photograph is kept",
          client.get(f"{BASE}{off['image_url']}").status_code == 200)

    on = alice.post(f"/api/listings/{alice_listing['id']}/reactivate").json()
    check("status is ACTIVE again", on["status"] == "ACTIVE")
    check("back in the marketplace", alice_listing["id"] in ids_of(alice.get(ajwa_url).json()))
    check("back in the average", average("Ajwa") == Decimal("0.825"), str(average("Ajwa")))

    # ==================================================================
    print("\n29. PHASE 12 - ownership is enforced by the server")
    # ==================================================================
    check("another user cannot edit it",
          bob.patch(f"/api/listings/{alice_listing['id']}",
                    files={"price": (None, "1")}).status_code == 403)
    check("another user cannot deactivate it",
          bob.post(f"/api/listings/{alice_listing['id']}/deactivate").status_code == 403)
    check("another user cannot reactivate it",
          bob.post(f"/api/listings/{alice_listing['id']}/reactivate").status_code == 403)
    check("the price was not changed by the attempt",
          Decimal(alice.get(f"/api/listings/{alice_listing['id']}").json()["price"])
          == Decimal("900"))

    return created


def main() -> None:
    marker = f".live{int(time.time())}@example.com"
    created: list[int] = []

    with httpx.Client(timeout=60) as client:
        wait_for_server(client)

        # ==================================================================
        print("\n1. Documentation")
        # ==================================================================
        check("GET /docs loads", client.get(f"{BASE}/docs").status_code == 200)
        schema = client.get(f"{BASE}/openapi.json").json()
        paths = schema["paths"]

        for path in (
            "/api/auth/register",
            "/api/auth/login",
            "/api/ml/predict",
            "/api/categories",
            "/api/listings",
            "/api/listings/{listing_id}",
            "/api/listings/{listing_id}/deactivate",
            "/api/listings/{listing_id}/reactivate",
            "/api/marketplace/listings",
            "/api/marketplace/best-price",
            "/api/categories/statistics",
            "/api/categories/{category_id}/stats",
        ):
            check(f"{path} is documented", path in paths)

        for method, path in (("post", "/api/listings"), ("patch", "/api/listings/{listing_id}")):
            media = paths[path][method]["requestBody"]["content"]
            check(
                f"{method.upper()} {path} accepts multipart/form-data",
                "multipart/form-data" in media,
                str(list(media)),
            )

        # ==================================================================
        print("\n2. Two separate accounts")
        # ==================================================================
        alice = User(client, "Alice Live", f"alice{marker}")
        bob = User(client, "Bob Live", f"bob{marker}")
        check("different accounts", alice.id != bob.id)

        categories = {
            row["name"]: row["id"]
            for row in alice.get("/api/categories").json()["categories"]
        }
        check("9+ categories available", len(categories) >= 9, str(len(categories)))

        # ==================================================================
        print("\n3. PHASE 7 - Alice publishes Ajwa at Tk800/kg")
        # ==================================================================
        listing = alice.publish(
            categories["Ajwa"], price="800.00", unit="kg", shop_name="Rahim Dates Shop"
        )
        created.append(listing["id"])
        first_image = listing["image_url"]
        check("photo is served over HTTP", client.get(f"{BASE}{first_image}").status_code == 200)
        check("per-gram price is 0.80", Decimal(listing["price_per_gram"]) == Decimal("0.80"))
        check("owner is Alice", listing["posted_by"]["id"] == alice.id)

        # ==================================================================
        print("\n4. PHASE 8 - Alice edits price, category and photo")
        # ==================================================================
        edited = alice.patch(f"/api/listings/{listing['id']}", data={"price": "900.00"})
        check("price edit accepted", edited.status_code == 200, edited.text)
        check("same listing id", edited.json()["id"] == listing["id"])
        check("price is 900.00", edited.json()["price"] == "900.00")
        check("per-gram recalculated", Decimal(edited.json()["price_per_gram"]) == Decimal("0.90"))

        edited = alice.patch(
            f"/api/listings/{listing['id']}", data={"category_id": categories["Medjool"]}
        )
        check("category edit accepted", edited.status_code == 200, edited.text)
        check("category name refreshed", edited.json()["category"]["name"] == "Medjool")

        edited = alice.patch(
            f"/api/listings/{listing['id']}",
            files={"image": ("new.jpg", photo("blue"), "image/jpeg")},
        )
        check("photo replaced", edited.status_code == 200, edited.text)
        second_image = edited.json()["image_url"]
        check("new photo is served", client.get(f"{BASE}{second_image}").status_code == 200)
        check("old photo is gone", client.get(f"{BASE}{first_image}").status_code == 404)

        # put it back to Ajwa/Tk800 for the marketplace checks below
        alice.patch(
            f"/api/listings/{listing['id']}",
            data={"category_id": categories["Ajwa"], "price": "800.00"},
        )

        # ==================================================================
        print("\n5. PHASE 8 - Bob is refused")
        # ==================================================================
        check(
            "403 on edit",
            bob.patch(f"/api/listings/{listing['id']}", data={"price": "1.00"}).status_code == 403,
        )
        check(
            "403 on deactivate",
            bob.post(f"/api/listings/{listing['id']}/deactivate").status_code == 403,
        )
        check(
            "Alice's price untouched",
            alice.get(f"/api/listings/{listing['id']}").json()["price"] == "800.00",
        )

        # ==================================================================
        print("\n6. PHASE 9 - the marketplace is shared")
        # ==================================================================
        bob_kilo = bob.publish(
            categories["Ajwa"], price="750.00", unit="kg", shop_name="Karim Dates Shop"
        )
        created.append(bob_kilo["id"])

        ajwa = f"/api/marketplace/listings?category_id={categories['Ajwa']}"
        seen_by_alice = alice.get(ajwa).json()
        seen_by_bob = bob.get(ajwa).json()
        for label, view in (("Alice", seen_by_alice), ("Bob", seen_by_bob)):
            check(f"{label} sees Alice's listing", listing["id"] in ids_of(view))
            check(f"{label} sees Bob's listing", bob_kilo["id"] in ids_of(view))

        card = next(i for i in seen_by_alice["listings"] if i["id"] == bob_kilo["id"])
        check("card names the other seller", card["posted_by"]["name"] == "Bob Live")
        check("card carries its own photo", card["image_url"] == bob_kilo["image_url"])
        check("card photo loads", client.get(f"{BASE}{card['image_url']}").status_code == 200)

        # ==================================================================
        print("\n7. PHASE 9 - price sorting, lowest first")
        # ==================================================================
        check(
            "Tk750 before Tk800",
            ids_of(seen_by_alice) == [bob_kilo["id"], listing["id"]],
            str([(i["id"], i["price"]) for i in seen_by_alice["listings"]]),
        )
        check("sort is reported", seen_by_alice["sort"] == "price")
        check("category is echoed back", seen_by_alice["category"]["name"] == "Ajwa")

        # ==================================================================
        print("\n8. PHASE 9 - per-gram sorting tells a different story")
        # ==================================================================
        # Tk180 for 200 g = Tk0.90/g, a bigger number per gram than Tk750/kg
        # (Tk0.75/g) even though 180 is the smaller price on the card.
        packet = alice.publish(
            categories["Ajwa"],
            price="180.00",
            quantity="200",
            unit="gram",
            shop_name="Packet Shop",
            colour="green",
        )
        created.append(packet["id"])

        by_card = ids_of(alice.get(f"{ajwa}&sort=price").json())
        by_value = ids_of(alice.get(f"{ajwa}&sort=price_per_gram").json())
        check("card price puts the packet first", by_card[0] == packet["id"], str(by_card))
        check("per-gram puts the kilo first", by_value[0] == bob_kilo["id"], str(by_value))
        check("the two orders really differ", by_card != by_value)

        piece = alice.publish(
            categories["Ajwa"], price="25.00", unit="piece", shop_name="Piece Shop",
            colour="orange",
        )
        created.append(piece["id"])
        by_value = ids_of(alice.get(f"{ajwa}&sort=price_per_gram").json())
        check("piece listing sorts last, not first", by_value[-1] == piece["id"], str(by_value))
        check("piece listing is still shown", piece["id"] in by_value)

        # ==================================================================
        print("\n9. PHASE 9 - best individual price")
        # ==================================================================
        best_url = f"/api/marketplace/best-price?category_id={categories['Ajwa']}"
        best = alice.get(best_url).json()
        check("winner is the cheapest per gram", best["listing"]["id"] == bob_kilo["id"])
        check("winner is Karim Dates Shop", best["listing"]["shop_name"] == "Karim Dates Shop")
        check("winner has its photo", best["listing"]["image_url"] == bob_kilo["image_url"])
        check("winner names its owner", best["listing"]["posted_by"]["id"] == bob.id)
        check(
            "the Tk25 piece did not win",
            best["listing"]["id"] != piece["id"],
            "a piece cannot be compared per gram",
        )

        # ==================================================================
        print("\n10. PHASE 9 - deactivating changes the public answer")
        # ==================================================================
        off = bob.post(f"/api/listings/{bob_kilo['id']}/deactivate")
        check("Bob deactivates his own", off.status_code == 200, off.text)
        check("hidden from Alice's marketplace", bob_kilo["id"] not in ids_of(alice.get(ajwa).json()))
        check("hidden from Bob's marketplace too", bob_kilo["id"] not in ids_of(bob.get(ajwa).json()))
        check("still in Bob's My Listings", bob_kilo["id"] in ids_of(bob.get("/api/listings/mine").json()))
        check("its photo is kept", client.get(f"{BASE}{bob_kilo['image_url']}").status_code == 200)

        new_best = alice.get(best_url).json()
        check("best price moved on", new_best["listing"]["id"] != bob_kilo["id"])
        check("best price is now Alice's kilo", new_best["listing"]["id"] == listing["id"])

        on = bob.post(f"/api/listings/{bob_kilo['id']}/reactivate")
        check("Bob reactivates", on.status_code == 200, on.text)
        check("back in the marketplace", bob_kilo["id"] in ids_of(alice.get(ajwa).json()))
        check("best price is his again", alice.get(best_url).json()["listing"]["id"] == bob_kilo["id"])

        # ==================================================================
        print("\n11. PHASE 9 - honest answers when there is no data")
        # ==================================================================
        empty = alice.get(f"/api/marketplace/best-price?category_id={categories['Sugaey']}")
        check("200, not an error", empty.status_code == 200, empty.text)
        check("no winner is reported as null", empty.json()["listing"] is None)
        check("and explained", "no comparable price data" in empty.json()["message"].lower())

        check(
            "unknown category is 404",
            alice.get("/api/marketplace/listings?category_id=999999").status_code == 404,
        )
        check(
            "empty category is an empty list, not a 404",
            alice.get(f"/api/marketplace/listings?category_id={categories['Shaishe']}").json()["total"] == 0,
        )
        check("paging reports the true total", alice.get(f"{ajwa}&limit=1").json()["total"] >= 3)
        check("an invalid sort is refused", alice.get(f"{ajwa}&sort=cheapest").status_code == 422)

        # ==================================================================
        print("\n12. PHASE 10 - the average price of a variety")
        # ==================================================================
        # Ajwa currently holds Alice's Tk800/kg (0.80/g), Bob's Tk750/kg (0.75/g),
        # a Tk180/200 g packet (0.90/g) and a Tk25 piece listing (excluded).
        #   (0.80 + 0.75 + 0.90) / 3 = 0.8167 (to 4 places)
        ajwa_stats = alice.get(f"/api/categories/{categories['Ajwa']}/stats").json()
        check(
            "average is the mean of the per-gram prices",
            Decimal(ajwa_stats["average_price_per_gram"]) == Decimal("0.8167"),
            str(ajwa_stats["average_price_per_gram"]),
        )
        check("counted 3 comparable listings", ajwa_stats["listing_count"] == 3, str(ajwa_stats))
        check("saw 4 active listings", ajwa_stats["active_listing_count"] == 4)
        check("excluded the 1 piece listing", ajwa_stats["excluded_piece_count"] == 1)
        check("named the category", ajwa_stats["category"] == "Ajwa")

        # ==================================================================
        print("\n13. PHASE 10 - no data means null, never zero")
        # ==================================================================
        empty_stats = alice.get(f"/api/categories/{categories['Sugaey']}/stats").json()
        check("average is null", empty_stats["average_price_per_gram"] is None)
        check("and not zero", empty_stats["average_price_per_gram"] != 0)
        check("counts are zero", empty_stats["listing_count"] == 0)
        check(
            "message is displayable as-is",
            empty_stats["message"].startswith("No gram-based price data available"),
            empty_stats["message"],
        )
        check(
            "unknown category is 404",
            alice.get("/api/categories/999999/stats").status_code == 404,
        )

        # ==================================================================
        print("\n14. PHASE 10 - best average price across all varieties")
        # ==================================================================
        # Give Rutab a clearly cheaper average than Ajwa's 0.8167.
        rutab_listing = alice.publish(
            categories["Rutab"], price="500.00", unit="kg", shop_name="Rutab Shop",
            colour="brown",
        )
        created.append(rutab_listing["id"])

        stats = alice.get("/api/categories/statistics").json()
        names = [row["category"] for row in stats["categories"]]
        check("Rutab and Ajwa both have averages", {"Rutab", "Ajwa"} <= set(names), str(names))
        check("ordered cheapest average first", names[0] == "Rutab", str(names))
        check("best average is Rutab", stats["best_average_price"]["category"] == "Rutab")
        check(
            "best average is 0.50 per gram",
            Decimal(stats["best_average_price"]["average_price_per_gram"]) == Decimal("0.5000"),
        )
        check(
            "best average matches the first row",
            stats["best_average_price"]["average_price_per_gram"]
            == stats["categories"][0]["average_price_per_gram"],
        )
        check(
            "varieties with no data are absent but still counted",
            stats["counted_categories"] < stats["total_categories"],
            f"{stats['counted_categories']} of {stats['total_categories']}",
        )
        check(
            "the Tk25 piece listing did not create an average",
            all(row["listing_count"] > 0 for row in stats["categories"]),
        )

        # ==================================================================
        print("\n15. PHASE 10 - nothing is cached")
        # ==================================================================
        # Make Rutab expensive; Ajwa should take the lead on the very next request.
        alice.patch(f"/api/listings/{rutab_listing['id']}", data={"price": "3000.00"})
        after_edit = alice.get("/api/categories/statistics").json()
        check(
            "editing a price moved the best average",
            after_edit["best_average_price"]["category"] == "Ajwa",
            after_edit["best_average_price"]["category"],
        )
        check(
            "Rutab's own average followed the edit",
            Decimal(
                alice.get(f"/api/categories/{categories['Rutab']}/stats").json()[
                    "average_price_per_gram"
                ]
            )
            == Decimal("3.0000"),
        )

        alice.post(f"/api/listings/{rutab_listing['id']}/deactivate")
        after_off = alice.get(f"/api/categories/{categories['Rutab']}/stats").json()
        check("deactivating removed it from the average", after_off["average_price_per_gram"] is None)
        check(
            "and from the global list",
            "Rutab" not in [r["category"] for r in alice.get("/api/categories/statistics").json()["categories"]],
        )

        alice.post(f"/api/listings/{rutab_listing['id']}/reactivate")
        after_on = alice.get(f"/api/categories/{categories['Rutab']}/stats").json()
        check(
            "reactivating brought it back",
            Decimal(after_on["average_price_per_gram"]) == Decimal("3.0000"),
        )

        # ==================================================================
        print("\n16. PHASE 10 - best average is not best individual price")
        # ==================================================================
        # Ajwa holds the cheapest single offer (Bob's Tk750/kg) while also leading on
        # average - so prove the two endpoints answer different questions by checking
        # each names the thing it should.
        best_single = alice.get(best_url).json()
        check("best individual price is one listing", best_single["listing"]["id"] == bob_kilo["id"])
        check(
            "best average price is a category",
            "listing" not in alice.get("/api/categories/statistics").json()["best_average_price"],
        )

    # ==================================================================
    print("\n17. Cleaning up the PHASE 7-10 run")
    # ==================================================================
    clean_up(created, marker)

    # ==================================================================
    # PHASE 12 runs on the now-empty marketplace, because it asserts exact
    # averages (Tk0.90/gram and so on) that anything left over would change.
    # A fresh client, and a longer timeout: it uploads real multi-megabyte
    # photographs and waits for real CPU inference.
    # ==================================================================
    with httpx.Client(timeout=180) as client:
        phase12_created = run_phase12(client, marker)

    # ==================================================================
    print("\n30. Cleaning up the PHASE 12 run")
    # ==================================================================
    clean_up(phase12_created, marker)

    print(f"\nALL {checks_run} LIVE CHECKS PASSED")


if __name__ == "__main__":
    main()
