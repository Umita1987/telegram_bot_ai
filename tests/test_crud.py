import pytest
from datetime import datetime, timezone
from sqlalchemy import text
from models.models import Post

@pytest.mark.asyncio(loop_scope="function")
async def test_create_post(db_session, test_user):
    new_post = Post(
        user_id=test_user.id,
        content="Test post",
        description="Test description",
        price="100",
        status="draft",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(new_post)
    await db_session.commit()
    assert new_post.id is not None

    result = await db_session.execute(
        text("SELECT content FROM posts WHERE id = :id"),
        {"id": new_post.id}
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "Test post"

@pytest.mark.asyncio(loop_scope="function")
async def test_update_post(db_session, test_user):
    post = Post(
        user_id=test_user.id,
        content="Update test",
        description="Initial description",
        price="100",
        status="draft",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(post)
    await db_session.commit()

    post.description = "Updated description"
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT description FROM posts WHERE id = :id"),
        {"id": post.id}
    )
    row = result.fetchone()
    assert row[0] == "Updated description"

@pytest.mark.asyncio(loop_scope="function")
async def test_delete_post(db_session, test_user):
    post = Post(
        user_id=test_user.id,
        content="Delete test",
        description="To be deleted",
        price="100",
        status="draft",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(post)
    await db_session.commit()
    post_id = post.id

    await db_session.delete(post)
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT id FROM posts WHERE id = :id"),
        {"id": post_id}
    )
    row = result.fetchone()
    assert row is None

@pytest.mark.asyncio(loop_scope="function")
async def test_transaction_rollback(db_session, test_user):
    post = Post(
        user_id=test_user.id,
        content="Rollback test",
        description="Before error",
        price="100",
        status="draft",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(post)
    await db_session.commit()
    post_id = post.id

    try:
        async with db_session.begin():
            post.description = "Updated in transaction"
            raise Exception("Искусственная ошибка")
    except Exception:
        pass

    result = await db_session.execute(
        text("SELECT description FROM posts WHERE id = :id"),
        {"id": post_id}
    )
    row = result.fetchone()
    # Ожидаем, что транзакция откатилась и описание осталось прежним
    assert row[0] == "Before error"
