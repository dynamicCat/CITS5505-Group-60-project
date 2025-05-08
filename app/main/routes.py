
from datetime import datetime
from sqlalchemy import func, desc
from flask import (
    abort, render_template, redirect, url_for, flash,
    request, jsonify
)
from flask_login import login_required, current_user
from collections import defaultdict
from datetime import datetime, date
from app import db
from app.models import MatchResult, ShareResult, User, MatchCalendar
from app.main import bp
from app.main.forms import MatchResultForm, UploadForm
import csv, io, json, logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@bp.route('/home')
def home():
    """
    Introductory landing page, public.
    """
    return render_template('main/home.html', is_authenticated=current_user.is_authenticated)

@bp.route('/')
def index():
    """
    Root: if logged in, go to home; otherwise to login.
    """
    if current_user.is_authenticated:
        return render_template('main/home.html', is_authenticated=True)
    return render_template('auth/login.html', is_authenticated=False)

@bp.route('/api/matches', methods=['GET'])
def get_matches():
    try:
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)
        if not all([year, month is not None]):
            return jsonify({'error': 'Year and month are required'}), 400

        if current_user.is_authenticated:
            # Fetch matches for the logged-in user for the specified year and month
            matches = MatchCalendar.query.filter(
                MatchCalendar.user_id == current_user.id,
                func.extract('month', MatchCalendar.match_date) == month,
                func.extract('year', MatchCalendar.match_date) == year
            ).all()
            matches_by_day = {str(match.match_date.day): match.to_dict() for match in matches}  # Ensure string keys
        else:
            # Return empty matches for public access
            matches_by_day = {}

        return jsonify(matches_by_day), 200

    except Exception as e:
        logger.error(f"Error fetching matches: {str(e)}")
        return jsonify({'error': f'Failed to fetch matches: {str(e)}'}), 500

@bp.route('/api/matches', methods=['POST'])
@login_required
def add_match():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        title = data.get('title')
        players = data.get('players')
        time = data.get('time')
        court = data.get('court')
        match_date_str = data.get('match_date')
        month = data.get('month')

        # Log the received data
        logger.info(f"Received match data from user {current_user.id}: title={title}, players={players}, time={time}, court={court}, match_date={match_date_str}, month={month}")

        # Validate inputs
        if not all([title, players, time, match_date_str, month]):
            return jsonify({'error': 'All fields are required'}), 400

        try:
            month = int(month)
            if not (1 <= month <= 12):
                return jsonify({'error': 'Month must be between 1 and 12'}), 400
        except (TypeError, ValueError):
            return jsonify({'error': 'Month must be a valid integer'}), 400

        # Validate time format (HH:MM)
        try:
            datetime.strptime(time, '%H:%M')
        except ValueError:
            return jsonify({'error': 'Time must be in HH:MM format (e.g., 14:00)'}), 400

        # Parse match date
        try:
            match_date = datetime.strptime(match_date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format, use YYYY-MM-DD'}), 400

        # Check for duplicate matches for this user
        existing_match = MatchCalendar.query.filter_by(
            user_id=current_user.id,
            match_date=match_date,
            time=time,
            court=court
        ).first()

        if existing_match:
            return jsonify({'error': 'A match already exists at this date, time, and court for this user'}), 400
        else:
            # Set default court if empty or invalid
            court = court.strip() if court else 'Court 1'

            # Create new match
            new_match = MatchCalendar(
                title=title,
                players=players,
                time=time,
                court=court,
                match_date=match_date,
                month=month + 1,  # Convert to 1-based for storage
                user_id=current_user.id
            )

            flash(f"New match created: {new_match}")

            db.session.add(new_match)
            db.session.commit()

            # Log successful storage
            logger.info(f"Match stored successfully: ID={new_match.id} for user {current_user.id}")

            return jsonify({
                'message': 'Match added successfully',
                'match': new_match.to_dict()
            }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding match for user {current_user.id}: {str(e)}")
        return jsonify({'error': f'Failed to add match: {str(e)}'}), 500

# upload part
@bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    manual_form = MatchResultForm(prefix='m')
    upload_form = UploadForm(prefix='u')


    users = User.query.order_by(User.username).all()
    choices = [(u.username, u.username) for u in users]
    manual_form.player1.choices = choices
    manual_form.player2.choices = choices

    # —— 1. Process CSV upload and preview ——
    if upload_form.validate_on_submit() and upload_form.submit_csv.data:
        # Read and parse CSV
        data = upload_form.csv_file.data.read().decode('utf-8')
        stream = io.StringIO(data)
        reader = csv.DictReader(stream)

        rows = []
        errors = []
        for idx, row in enumerate(reader, start=1):
            # Check for empty fields
            missing = [k for k, v in row.items() if not v or v.strip() == '']
            if missing:
                errors.append((idx, missing))
            rows.append(row)

        # Serialize and pass to the preview page
        rows_json = json.dumps(rows)
        return render_template(
            'main/preview_upload.html',
            rows=rows,
            rows_json=rows_json,
            errors=errors
        )

    # —— 2. Handle manual entry ——
    if manual_form.submit_manual.data and manual_form.validate_on_submit():
        p1 = manual_form.player1.data
        p2 = manual_form.player2.data
        s1 = manual_form.score1.data
        s2 = manual_form.score2.data

        if s1 == s2:
            flash('⚠️ There is no tied game in Tennis, please check again the result', 'danger')
            return redirect(url_for('main.upload'))

        winner = p1 if s1 > s2 else p2
        score_str = f"{s1}-{s2}"

        m = MatchResult(
            tournament_name=manual_form.tournament_name.data,
            player1=p1,
            player2=p2,
            score=score_str,
            winner=winner,
            match_date=manual_form.match_date.data or datetime.utcnow(),
            user_id=current_user.id
        )
        db.session.add(m)
        db.session.commit()
        flash('✅ Single record submitted successfully!', 'success')
        return redirect(url_for('main.view_stats'))


    # —— GET or verification failure ——
    return render_template(
        'main/upload.html',
        manual_form=manual_form,
        upload_form=upload_form,
        today=date.today().isoformat()
    )

@bp.route('/upload/confirm', methods=['POST'])
@login_required
def upload_confirm():
    rows = json.loads(request.form.get('rows_json','[]'))
    if request.form.get('action') == 'selected':
        idxs = request.form.getlist('selected')
        rows = [rows[int(i)] for i in idxs]
    count = 0
    for r in rows:
        try:
            m = MatchResult(
                tournament_name=r['tournament_name'],
                match_date=datetime.strptime(r['match_date'], '%Y-%m-%d'),
                player1=r['player1'],
                player2=r['player2'],
                score=r['score'],
                winner=r['winner'],
                user_id=current_user.id
            )
            db.session.add(m)
            count += 1
        except:
            continue
    db.session.commit()
    flash(f'✅ Successfully imported {count} records.', 'success')
    return redirect(url_for('main.view_stats'))

# view_stats part
@bp.route('/view_stats')
@login_required
def view_stats():
    # —— 1. Personal (own + private sharing) ——
    own = (MatchResult.query
           .filter_by(user_id=current_user.id)
           .order_by(desc(MatchResult.match_date))
           .all())
    private_shared = [
        sr.match_result for sr in
        ShareResult.query
                   .filter_by(recipient_id=current_user.id, is_public=False)
                   .order_by(desc(ShareResult.timestamp))
                   .all()
    ]
    personal = sorted(own + private_shared,
                      key=lambda r: r.match_date, reverse=True)

    total = len(personal)
    wins  = sum(1 for r in personal if r.winner == current_user.username)
    losses = total - wins
    stats = {
        'total_matches':  total,
        'win_count':      wins,
        'win_percentage': f"{(wins/total*100):.1f}%" if total else "0.0%",
        'win_loss_ratio': f"{(wins/losses):.2f}" if losses else f"{wins:.2f}"
    }
    rev = list(reversed(personal))
    chart_labels = [r.match_date.strftime('%b %Y') for r in rev]
    chart_won    = [1 if r.winner == current_user.username else 0 for r in rev]
    chart_lost   = [1 if r.winner != current_user.username else 0 for r in rev]
    recent5      = personal[:5]

    # —— 2. Global public sharing statistics ——
    # Count the number of public shares by month (Bar Chart)
    monthly = (
        db.session.query(
            func.strftime('%Y-%m', MatchResult.match_date).label('month'),
            func.count(MatchResult.id).label('cnt')
        )
        .join(ShareResult, ShareResult.match_result_id == MatchResult.id)
        .filter(ShareResult.is_public == True)
        .group_by('month')
        .order_by('month')
        .all()
    )
    public_months = [m.month for m in monthly]
    public_counts = [m.cnt   for m in monthly]

    # Find the Top N popular winners (Bar & Pie)
    winners = (
        db.session.query(
            MatchResult.winner, func.count(MatchResult.id).label('cnt')
        )
        .join(ShareResult, ShareResult.match_result_id == MatchResult.id)
        .filter(ShareResult.is_public == True)
        .group_by(MatchResult.winner)
        .order_by(desc(func.count(MatchResult.id)))
        .limit(5)
        .all()
    )
    public_labels = [w.winner for w in winners]
    public_wins   = [w.cnt    for w in winners]

    # Trend of monthly wins of popular winners (Line Chart with regression exploration)
    # First take out all (month, winner, cnt) records
    monthly_wins_all = (
        db.session.query(
            func.strftime('%Y-%m', MatchResult.match_date).label('month'),
            MatchResult.winner,
            func.count(MatchResult.id).label('cnt')
        )
        .join(ShareResult, ShareResult.match_result_id == MatchResult.id)
        .filter(ShareResult.is_public == True,
                MatchResult.winner.in_(public_labels))
        .group_by('month', MatchResult.winner)
        .order_by('month')
        .all()
    )
    # Construct dictionary
    monthly_trends = {w: [0] * len(public_months) for w in public_labels}
    for rec in monthly_wins_all:
        month, winner, cnt = rec
        idx = public_months.index(month)
        monthly_trends[winner][idx] = cnt
    # —— 3. Site-wide user ranking ——
    user_win_counts = (
        db.session.query(MatchResult.winner, func.count(MatchResult.id).label('win_count'))
        .group_by(MatchResult.winner)
        .order_by(desc('win_count'))
        .all()
    )
    global_ranking = [{ 'username': u[0], 'win_count': u[1] } for u in user_win_counts]
    user_rank = next((i + 1 for i, u in enumerate(global_ranking) if u['username'] == current_user.username), None)
    

    return render_template(
        'main/view_stats.html',
        # Private Section
        stats=stats,
        chart_labels=chart_labels,
        chart_won=chart_won,
        chart_lost=chart_lost,
        recent_results=recent5,
        user_rank=user_rank,
        global_ranking=global_ranking,
        # Public part
        public_months=public_months,
        public_counts=public_counts,
        public_labels=public_labels,
        public_wins=public_wins,
        monthly_trends=monthly_trends
        
    )

#received_results part
@bp.route('/received_results')
@login_required
def received_results():
    # Private sharing: others send to the current user
    private_ids = (
        db.session.query(ShareResult.match_result_id)
        .filter(ShareResult.recipient_id == current_user.id, ShareResult.is_public == False)
        .subquery()
    )
    private_matches = (
        MatchResult.query
        .filter(MatchResult.id.in_(private_ids))
        .order_by(MatchResult.match_date.desc())
        .all()
    )

    # Public sharing: shared by everyone
    public_ids = (
        db.session.query(ShareResult.match_result_id)
        .filter(ShareResult.is_public == True)
        .subquery()
    )
    public_matches = (
        MatchResult.query
        .filter(MatchResult.id.in_(public_ids))
        .order_by(MatchResult.match_date.desc())
        .all()
    )

    return render_template(
        'main/received_results.html',
        private_matches=private_matches,
        public_matches=public_matches
    )

@bp.route('/api/users')
@login_required
def api_users():
    """
    Return list of all usernames for share dropdown.
    """
    users = User.query.with_entities(User.username).order_by(User.username).all()
    return jsonify([u[0] for u in users])

@bp.route('/api/match_dates')
@login_required
def api_match_dates():
    """
    Return list of distinct match_date strings for this user.
    """
    dates = (
        db.session.query(func.date(MatchResult.match_date))
                  .filter_by(user_id=current_user.id)
                  .distinct()
                  .order_by(desc(MatchResult.match_date))
                  .all()
    )
    return jsonify([d[0].strftime('%Y-%m-%d') for d in dates])

@bp.route('/api/matches_by_date')
@login_required
def api_matches_by_date():
    """
    Given ?date=YYYY-MM-DD, return JSON list of this user's matches on that date.
    """
    date_str = request.args.get('date')
    if not date_str:
        return jsonify([])
    dt = datetime.strptime(date_str, '%Y-%m-%d').date()
    matches = (
        MatchResult.query
                   .filter_by(user_id=current_user.id)
                   .filter(func.date(MatchResult.match_date)==dt)
                   .order_by(desc(MatchResult.match_date))
                   .all()
    )
    return jsonify([
        {'id': m.id, 'title': f'{m.player1} vs {m.player2} ({m.score})'}
        for m in matches
    ])
    
#share part
@bp.route('/share', methods=['GET', 'POST'])
@login_required
def share():
    if request.method == 'GET':
        # 1) The current user's own game list
        match_results = (
            MatchResult.query
            .filter_by(user_id=current_user.id)
            .order_by(desc(MatchResult.match_date))
            .all()
        )
        # 2) The current user's sharing history (both public and private)
        share_history = (
            ShareResult.query
            .filter_by(sender_id=current_user.id)
            .order_by(desc(ShareResult.timestamp))
            .limit(5)
            .all()
        )
        # 3) All other users → Private sharing pulls down and the page is rendered
        all_users = User.query.filter(User.id != current_user.id).order_by(User.username).all()
        all_users_data = [{'id': u.id, 'username': u.username} for u in all_users]
 
        # 4) Construct a private sharing mapping
        shared_map = {}
        private_recs = ShareResult.query.filter_by(
            sender_id=current_user.id, is_public=False
        ).all()
        for s in private_recs:
            shared_map.setdefault(s.match_result_id, set()).add(s.recipient_id)
        # Convert to list for JSON serialization
        shared_map = {mid: list(rids) for mid, rids in shared_map.items()}
 
        # 5) Construct a list of publicly shared competition IDs
        public_recs = ShareResult.query.filter_by(
            sender_id=current_user.id, is_public=True
        ).all()
        public_shared_ids = [s.match_result_id for s in public_recs]
 
        # Rendering Template
        return render_template(
            'main/share.html',
            match_results=match_results,
            share_history=share_history,
            all_users_data=all_users_data,
            shared_map=shared_map,
            public_shared_ids=public_shared_ids,
            current_username=current_user.username
        )
 
    # —— POST (AJAX) ——
    data = request.get_json() or {}
    match_ids = list(map(int, data.get('match_ids', [])))
    usernames = data.get('usernames', [])
    is_public = data.get('public', False)
 
    if not match_ids:
        return jsonify({'message': 'No matches selected.'}), 400
 
    # Public sharing: only insert those that have not been made public before
    if is_public:
        added = 0
        for mid in match_ids:
            exists = ShareResult.query.filter_by(
                match_result_id=mid,
                sender_id=current_user.id,
                is_public=True
            ).first()
            if not exists:
                db.session.add(ShareResult(
                    match_result_id=mid,
                    sender_id=current_user.id,
                    is_public=True
                ))
                added += 1
        db.session.commit()
        return jsonify({'result': 'shared_public'}), 200
 
    # Private sharing: skip yourself and shared groups
    if not usernames:
        return jsonify({'message': 'No recipients selected.'}), 400
 
    recipients = User.query.filter(User.username.in_(usernames)).all()
    added = 0
    for u in recipients:
        if u.id == current_user.id:
            continue
        for mid in match_ids:
            exists = ShareResult.query.filter_by(
                match_result_id=mid,
                sender_id=current_user.id,
                recipient_id=u.id,
                is_public=False
            ).first()
            if not exists:
                db.session.add(ShareResult(
                    match_result_id=mid,
                    sender_id=current_user.id,
                    recipient_id=u.id,
                    is_public=False
                ))
                added += 1
 
    db.session.commit()
    if added:
        return jsonify({'result': 'shared_private'}), 200
    else:
        return jsonify({'message': 'Nothing new to share.'}), 400
    
@bp.route('/unshare/<int:share_id>', methods=['POST'])
@login_required
def unshare(share_id):
    sr = ShareResult.query.get_or_404(share_id)
    if sr.sender_id != current_user.id:
        abort(403)
 
    db.session.delete(sr)
    db.session.commit()
    flash('Share record removed.', 'info')
    return redirect(url_for('main.share'))
 