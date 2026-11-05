import React, { useState } from 'react'
import { Button, Empty, Modal, duration, field, stamp } from './ui'

export function PartyForm({ close, act }) {
  return <Modal title="Add party" close={close}><form onSubmit={async e => {
    e.preventDefault()
    if (await act('/queue', 'POST', { name: field(e.currentTarget, 'name'), size: Number(field(e.currentTarget, 'size')) }, 'Party added to the waitlist.')) close()
  }}><label>Party name<input name="name" maxLength="80" required autoFocus/></label>
    <label>Guests<input name="size" type="number" min="1" max="60" defaultValue="2" required/></label>
    <div className="form-actions"><Button type="button" onClick={close}>Cancel</Button><Button variant="primary" type="submit">Add to waitlist</Button></div>
  </form></Modal>
}

export function SeatForm({ close, act, party, tables }) {
  const options = party.suggested.map(id => tables.find(table => table.id === id)).filter(Boolean)
  return <Modal title={'Assign ' + party.name} close={close}><form onSubmit={async e => {
    e.preventDefault()
    const body = { table: Number(field(e.currentTarget, 'table')), action: e.nativeEvent.submitter?.value || 'seat' }
    if (await act('/queue/' + party.id + '/assign', 'POST', body, body.action === 'call' ? 'Table held for ten minutes. Call the party from the host stand.' : 'Party seated. The service timer has started.')) close()
  }}><p>{party.size} guests · Best-fit tables appear first.</p>
    {options.length ? <label>Available table<select name="table" defaultValue={party.table_id || options[0].id}>{options.map(t => <option value={t.id} key={t.id}>{t.name} · {t.capacity} seats</option>)}</select></label> : <Empty>No available table fits this party.</Empty>}
    <div className="form-actions"><Button type="button" onClick={close}>Close</Button><Button type="submit" value="call" disabled={!options.length}>Hold and call</Button><Button type="submit" value="seat" variant="primary" disabled={!options.length}>Seat now</Button></div>
  </form></Modal>
}

export function Waitlist({ state, act, chooseParty }) {
  return <section className="panel"><div className="panel-head"><h2>Waiting parties ({state.queue.length})</h2></div>
    {state.queue.length ? <div className="scroll"><table><thead><tr><th>Party</th><th>Guests</th><th>Wait</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>{state.queue.map(p => <tr key={p.id}><td><strong>{p.name}</strong></td><td>{p.size}</td><td>{duration(state.now - p.joined)}</td><td>{p.status === 'called' ? 'Called · ' + (state.tables.find(t => t.id === p.table_id)?.name || '') : p.suggested.length ? 'Table available' : 'Waiting'}</td>
        <td><div className="actions"><Button variant="primary compact" disabled={!p.suggested.length} onClick={() => chooseParty(p)}>Assign table</Button><Button variant="compact" onClick={() => act('/queue/' + p.id, 'DELETE', undefined, 'Party removed.')}>Remove</Button></div></td></tr>)}</tbody>
    </table></div> : <Empty icon="people">No parties are waiting. Add a party when guests arrive.</Empty>}
  </section>
}

function localInput(date) {
  return new Date(date - new Date(date).getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export function ReservationForm({ close, act, tables }) {
  return <Modal title="New reservation" close={close}><form onSubmit={async e => {
    e.preventDefault()
    const form = e.currentTarget
    const start = new Date(field(form, 'start'))
    const end = new Date(start.getTime() + 60000 * Number(field(form, 'length')))
    if (await act('/reservations', 'POST', { name: field(form, 'name'), size: Number(field(form, 'size')), table: Number(field(form, 'table')), start: start.toISOString(), end: end.toISOString() }, 'Reservation booked.')) close()
  }}><label>Party name<input name="name" required maxLength="80" autoFocus/></label><div className="two">
    <label>Guests<input name="size" type="number" min="1" max="60" required defaultValue="2"/></label>
    <label>Table<select name="table" aria-label="Reservation table" required>{tables.map(t => <option key={t.id} value={t.id}>{t.name} · {t.capacity} seats</option>)}</select></label>
  </div><div className="two">
    <label>Arrival time<input name="start" type="datetime-local" required defaultValue={localInput(Date.now() + 3600000)}/></label>
    <label>Duration (minutes)<input name="length" type="number" required min="15" max="480" defaultValue="90"/></label>
  </div><div className="form-actions"><Button type="button" onClick={close}>Cancel</Button><Button variant="primary" type="submit" disabled={!tables.length}>Book reservation</Button></div></form></Modal>
}

export function Reservations({ state, act }) {
  return <section className="panel"><div className="panel-head"><h2>Reservations</h2></div>{state.reservations.length ?
    <div className="scroll"><table><thead><tr><th>Party</th><th>Guests</th><th>Table</th><th>Arrival</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>{state.reservations.map(r => <tr key={r.id}><td><strong>{r.name}</strong></td><td>{r.size}</td><td>{r.table_name}</td><td className="nowrap">{stamp(r.start)}</td><td>{r.status.replace('_', ' ')}</td><td>
        {r.status === 'booked' && <div className="actions"><Button variant="primary compact" disabled={state.now < r.start - 900} onClick={() => act('/reservations/' + r.id + '/seat', 'POST', undefined, 'Reservation seated.')}>Seat now</Button><Button variant="compact" onClick={() => act('/reservations/' + r.id + '/cancel', 'POST', undefined, 'Reservation cancelled.')}>Cancel booking</Button></div>}
      </td></tr>)}</tbody></table></div> : <Empty icon="calendar">No recent or upcoming reservations.</Empty>}
  </section>
}

export { Analytics } from './owner-report'
