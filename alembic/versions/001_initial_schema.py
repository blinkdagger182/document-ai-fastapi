"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('storage_key_original', sa.String(), nullable=False),
        sa.Column('storage_key_filled', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('imported', 'processing', 'ready', 'filling', 'filled', 'failed', name='documentstatus'), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('hash_fingerprint', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_documents_user_id', 'documents', ['user_id'])
    op.create_index('ix_documents_status', 'documents', ['status'])
    op.create_index('ix_documents_hash_fingerprint', 'documents', ['hash_fingerprint'])
    
    # Create field_regions table
    op.create_table(
        'field_regions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('page_index', sa.Integer(), nullable=False),
        sa.Column('x', sa.Float(), nullable=False),
        sa.Column('y', sa.Float(), nullable=False),
        sa.Column('width', sa.Float(), nullable=False),
        sa.Column('height', sa.Float(), nullable=False),
        sa.Column('field_type', sa.Enum('text', 'multiline', 'checkbox', 'date', 'number', 'signature', 'unknown', name='fieldtype'), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('template_key', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_field_regions_document_id', 'field_regions', ['document_id'])
    op.create_index('ix_field_regions_template_key', 'field_regions', ['template_key'])
    
    # Create field_values table
    op.create_table(
        'field_values',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('field_region_id', UUID(as_uuid=True), sa.ForeignKey('field_regions.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('source', sa.Enum('manual', 'autofill', 'ai', name='fieldsource'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_field_values_document_id', 'field_values', ['document_id'])
    op.create_index('ix_field_values_field_region_id', 'field_values', ['field_region_id'])
    op.create_index('ix_field_values_user_id', 'field_values', ['user_id'])
    
    # Create usage_events table
    op.create_table(
        'usage_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('event_type', sa.Enum('ocr_run', 'pdf_compose', 'pages_processed', name='eventtype'), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_usage_events_user_id', 'usage_events', ['user_id'])
    op.create_index('ix_usage_events_event_type', 'usage_events', ['event_type'])
    op.create_index('ix_usage_events_created_at', 'usage_events', ['created_at'])


def downgrade() -> None:
    op.drop_table('usage_events')
    op.drop_table('field_values')
    op.drop_table('field_regions')
    op.drop_table('documents')
    op.drop_table('users')
    
    op.execute('DROP TYPE IF EXISTS eventtype')
    op.execute('DROP TYPE IF EXISTS fieldsource')
    op.execute('DROP TYPE IF EXISTS fieldtype')
    op.execute('DROP TYPE IF EXISTS documentstatus')
