from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from realty.actions import propose
from realty.config import settings
from realty.db import SessionLocal, now
from realty.models import (
    Activity,
    Appointment,
    Communication,
    Contact,
    Deal,
    Fact,
    Membership,
    Notification,
    Organization,
    Preference,
    Property,
    Subscription,
    Task,
    Transaction,
    User,
    Workflow,
)
from realty.schemas import ActionInput
from realty.security import Principal, hash_password

DEMO_EMAIL = "sarah@realty.example.com"
DEMO_PASSWORD = "RealtyAI-demo-2026!"


def seed() -> None:
    if not settings.demo_mode or settings.app_env == "production":
        raise RuntimeError("Seed data is allowed only in a dedicated demo environment")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == DEMO_EMAIL)):
            return
        org = Organization(name="Northstar Realty", is_demo=True)
        user = User(
            name="Sarah Mitchell", email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD)
        )
        db.add_all([org, user])
        db.flush()
        db.info["org_id"] = org.id
        db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
        db.add(Subscription(org_id=org.id, trial_end=now() + timedelta(days=14)))
        actor = Principal(user.id, org.id, "owner")
        contact_specs = [
            (
                "John & Emma Wilson",
                "john.wilson@example.com",
                "buyer",
                "active",
                88,
                2,
                700000,
                "West Hartford",
            ),
            (
                "Olivia Chen",
                "olivia.chen@example.com",
                "buyer",
                "qualified",
                82,
                9,
                550000,
                "Hartford",
            ),
            ("Michael Brooks", "michael.brooks@example.com", "seller", "active", 76, 3, None, None),
            (
                "Ava Thompson",
                "ava.thompson@example.com",
                "lead",
                "new",
                72,
                1,
                480000,
                "Farmington",
            ),
            (
                "Daniel Rivera",
                "daniel.rivera@example.com",
                "buyer",
                "nurturing",
                64,
                12,
                800000,
                "West Hartford",
            ),
            (
                "Sophie Williams",
                "sophie.williams@example.com",
                "seller",
                "active",
                90,
                1,
                None,
                None,
            ),
            ("James Parker", "james.parker@example.com", "lead", "new", 45, 8, None, None),
            (
                "Isabella Moore",
                "isabella.moore@example.com",
                "buyer",
                "qualified",
                79,
                4,
                625000,
                "Avon",
            ),
        ]
        contacts: list[Contact] = []
        for name, email, kind, stage, score, days, budget, location in contact_specs:
            contact = Contact(
                org_id=org.id,
                name=name,
                email=email,
                phone="+1 860 555 01" + str(len(contacts)).zfill(2),
                kind=kind,
                stage=stage,
                score=score,
                score_reason="Seeded demo assessment; verify intent with the client.",
                last_contact_at=now() - timedelta(days=days),
            )
            db.add(contact)
            db.flush()
            contacts.append(contact)
            if budget:
                pref = Preference(
                    org_id=org.id,
                    contact_id=contact.id,
                    budget_min=budget - 150000,
                    budget_max=budget,
                    location=location,
                    bedrooms=3,
                    bathrooms=2,
                    property_type="single_family",
                    timeline="Within 3 months",
                    features=["garage", "garden"],
                    financing="Pre-approval in progress",
                )
                db.add(pref)
                db.add(
                    Fact(
                        org_id=org.id,
                        contact_id=contact.id,
                        field="budget_max",
                        value=budget,
                        confidence=1,
                        source_type="manual",
                        method="demo_seed",
                        state="confirmed",
                        verified_by=user.id,
                    )
                )
            db.add(
                Activity(
                    org_id=org.id,
                    contact_id=contact.id,
                    kind="note",
                    title="Relationship started",
                    body="Fictional demo relationship. All records in this workspace are sample data.",
                    created_at=now() - timedelta(days=21),
                )
            )
        properties: list[Property] = []
        for address, location, price, beds, baths, sqft in [
            ("24 Maplewood Drive", "West Hartford", 675000, 4, 2.5, 2480),
            ("18 Birch Lane", "Farmington", 459000, 3, 2, 1860),
            ("102 Prospect Avenue", "Hartford", 525000, 3, 2.5, 2140),
            ("8 Meadowbrook Court", "Avon", 615000, 4, 3, 2760),
        ]:
            prop = Property(
                org_id=org.id,
                address=address,
                location=location,
                price=price,
                bedrooms=beds,
                bathrooms=baths,
                sqft=sqft,
                features=["garage", "garden", "home office"],
                source="fictional_demo",
                contact_id=contacts[2].id if not properties else contacts[5].id,
            )
            db.add(prop)
            db.flush()
            properties.append(prop)
        for index, stage in enumerate(["showing", "offer", "under_contract", "qualified"]):
            deal = Deal(
                org_id=org.id,
                contact_id=contacts[index].id,
                property_id=properties[index].id,
                title=properties[index].address,
                stage=stage,
                value=properties[index].price,
                expected_close=now() + timedelta(days=14 + index * 7),
            )
            db.add(deal)
            db.flush()
            db.add(
                Transaction(
                    org_id=org.id,
                    deal_id=deal.id,
                    title="Confirm financing",
                    kind="milestone",
                    due_at=now() + timedelta(days=3 + index),
                )
            )
        today = (
            now()
            .replace(tzinfo=UTC)
            .astimezone(ZoneInfo(org.timezone))
            .replace(hour=10, minute=0, second=0, microsecond=0)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
        for index, title in enumerate(
            ["Maplewood Drive showing", "Olivia · buyer consultation", "Michael · listing review"]
        ):
            db.add(
                Appointment(
                    org_id=org.id,
                    contact_id=contacts[index].id,
                    title=title,
                    start_at=today + timedelta(hours=index * 2),
                    end_at=today + timedelta(hours=index * 2 + 1),
                    location=properties[index].address,
                    owner_id=user.id,
                )
            )
        for index, title in enumerate(
            [
                "Send inspection checklist to Olivia",
                "Review the Wilsons' financing",
                "Collect showing feedback",
                "Confirm photography for Michael",
            ]
        ):
            db.add(
                Task(
                    org_id=org.id,
                    contact_id=contacts[index].id,
                    assigned_to=user.id,
                    title=title,
                    due_at=now() + timedelta(days=index - 1),
                    priority="high" if index < 2 else "normal",
                )
            )
        for index, (subject, body) in enumerate(
            [
                (
                    "Loved the Maplewood house",
                    "Hi Sarah, we loved the light at Maplewood. Our budget is up to $725,000 and we need 4 bedrooms. Is a second showing possible this weekend? Thanks, John",
                ),
                (
                    "A quick update on our search",
                    "Hi Sarah, we are still looking in Hartford. I'll send you the pre-approval tomorrow. Our budget is $550,000. Thanks, Olivia",
                ),
                (
                    "Feedback from the weekend",
                    "Hi Sarah, what did buyers think after the showings? We would love to hear feedback about the kitchen. Thanks, Michael",
                ),
            ]
        ):
            message = Communication(
                org_id=org.id,
                owner_id=user.id,
                contact_id=contacts[index].id,
                sender=contacts[index].email or "",
                recipient=DEMO_EMAIL,
                subject=subject,
                body=body,
                received_at=now() - timedelta(hours=index + 1),
                thread_id="demo-thread-" + str(index),
            )
            db.add(message)
            db.flush()
            db.add(
                Activity(
                    org_id=org.id,
                    contact_id=contacts[index].id,
                    kind="email",
                    title=subject,
                    body=body,
                    source_id=message.id,
                )
            )
            if index == 0:
                propose(
                    db,
                    actor,
                    ActionInput(
                        kind="crm_update",
                        title="The Wilsons updated their budget",
                        reason="John wrote: “Our budget is up to $725,000”. Confirm before updating the profile.",
                        contact_id=contacts[0].id,
                        confidence=0.85,
                        source_id=message.id,
                        priority="high",
                        payload={"contact_id": contacts[0].id, "changes": {"budget_max": 725000}},
                    ),
                    "demo:budget",
                )
        from realty.jobs import followup

        followup(db, actor, contacts[1], "demo:followup")
        propose(
            db,
            actor,
            ActionInput(
                kind="create_task",
                title="Prepare for Michael's listing review",
                reason="A listing review is on today's calendar. Bring the recent showing feedback.",
                contact_id=contacts[2].id,
                payload={
                    "title": "Prepare showing feedback for Michael",
                    "contact_id": contacts[2].id,
                    "priority": "high",
                },
            ),
            "demo:task",
        )
        db.add(
            Notification(
                org_id=org.id,
                title="Your workspace is ready",
                body="Explore the sample relationships, then review your assistant's suggestions.",
                link="/actions",
            )
        )
        db.add(
            Workflow(
                org_id=org.id,
                name="Keep warm relationships moving",
                trigger="FOLLOW_UP_REQUIRED",
                action="recommend_followup",
                condition={"min_score": 60},
            )
        )
        db.commit()


if __name__ == "__main__":
    seed()
    print("Demo workspace seeded. Sign in as sarah@realty.example.com / RealtyAI-demo-2026!")
